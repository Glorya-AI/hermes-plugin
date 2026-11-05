"""The Glorya plugin's runtime: hooks, native tools and shared state, built once per ``register``."""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import media, render
from .client import CREATE_TOOLS, JOB_TOOLS, Glorya, GloryaError, parse_tool_result
from .follower import Follower, current_session
from .settings import Settings, load
from .store import TERMINAL, Store

logger = logging.getLogger(__name__)

KIND_BY_TOOL = {tool: kind for kind, tool in CREATE_TOOLS.items()}
CONTEXT_WINDOW_SECONDS = 2 * 3600
FOLLOW_NOTE = (
    "The Hermes Glorya plugin is following this job. It updates a progress message in this chat, posts Glorya's "
    "questions, and posts the finished files here by itself. Tell the user in one short sentence that Glorya "
    "started and share open_url, then end your turn. Don't call get_job for this job."
)
DESKTOP_NOTE = ' In this desktop chat, also put the line ::glorya-job{{id="{job_id}"}} in your reply: it shows a live Glorya card.'


def _plugin_data_dir() -> Path:
    from plugins.plugin_storage import plugin_data_dir
    return plugin_data_dir("glorya")


def _plugin_db():
    from plugins.plugin_storage import plugin_db
    return plugin_db("glorya")


def mcp_connected(server: str) -> bool:
    """False only when Hermes reports the server missing from config, signed out or failed; unknown counts as connected."""
    try:
        from hermes_cli.config import load_config_readonly
        from tools.mcp_tool_discovery import mcp_servers_not_connected
        servers = (load_config_readonly() or {}).get("mcp_servers") or {}
        return server in servers and server not in mcp_servers_not_connected()
    except Exception:
        return True


NOT_CONNECTED = (
    "[Glorya plugin] Glorya isn't connected in Hermes right now, so the mcp__{server}__ tools are missing. "
    "Don't search for them, change settings or run commands: signing in needs the user's own browser. "
    "If the user wants Glorya, tell them in one line to run `hermes glorya setup` in their own terminal, "
    "then start a new chat.")


class GloryaPlugin:
    def __init__(self, ctx: Any, *, store: Optional[Store] = None, data_dir: Optional[Callable[[], Path]] = None,
                 clock: Callable[[], float] = time.time, follower: Optional[Follower] = None,
                 session: Callable[..., Any] = current_session, fetch: Callable[..., Any] = media.fetch_assets,
                 connected: Callable[[str], bool] = mcp_connected):
        self.ctx = ctx
        self.clock = clock
        self.session = session
        self.fetch = fetch
        self.connected = connected
        if data_dir is None:
            # Resolved now, while this profile's home is active: a multiplexed gateway runs several.
            root = _plugin_data_dir()
            data_dir = lambda: root  # noqa: E731
        self.data_dir = data_dir
        if store is None:
            connection = _plugin_db()
            store = Store(lambda: connection, clock=clock)
        self.store = store
        self.follower = follower or Follower(ctx, self.store, self.settings, self.glorya, data_dir, clock=clock,
                                             session=session, fetch=fetch)

    def housekeep(self) -> None:
        """Drop finished jobs older than 30 days and their downloaded files (once per process)."""
        if getattr(self, "_housekept", False):
            return
        self._housekept = True
        try:
            media_root = self.data_dir() / "media"
            for job_id in self.store.prune():
                folder = media_root / job_id
                if folder.is_dir() and folder.parent == media_root:
                    shutil.rmtree(folder, ignore_errors=True)
        except Exception:
            logger.debug("glorya: housekeeping failed", exc_info=True)

    def settings(self) -> Settings:
        return load(self.ctx)

    def glorya(self) -> Glorya:
        return Glorya(self.ctx, self.settings().server)

    def _tool(self, tool_name: str) -> Optional[str]:
        prefix = f"mcp__{self.settings().server}__"
        return tool_name[len(prefix):] if tool_name.startswith(prefix) else None

    # -- hooks ----------------------------------------------------------------------------------

    def on_transform_tool_result(self, tool_name: str = "", args: Optional[dict] = None, result: Any = None,
                                 **_: Any) -> Optional[str]:
        """After a Glorya create/refine/respond/publish call: follow the job and tell the model it
        need not poll. Returns the rewritten result, or None to leave it unchanged."""
        try:
            tool = self._tool(tool_name or "")
            if tool is None:
                return None
            data = parse_tool_result(result)
            if data is None:
                return None
            job_id = str(data.get("job_id") or (args or {}).get("job_id") or "")
            if tool == "get_job":
                if job_id and self.store.get(job_id):
                    self.store.save_view(job_id, data)
                return None
            if tool not in JOB_TOOLS or not job_id:
                return None
            known = self.store.get(job_id)
            kind = str(data.get("kind") or (known.kind if known else "") or KIND_BY_TOOL.get(tool, ""))
            title = str(data.get("title") or (known.title if known else ""))
            self.housekeep()
            if not self.follower.start(job_id, kind=kind, title=title, open_url=str(data.get("open_url") or ""),
                                       source="agent"):
                return None
            note = FOLLOW_NOTE
            if self.ctx.session_surface() == "desktop":
                note += DESKTOP_NOTE.format(job_id=job_id)
            data = {**data, "next_step": note, "followed_by_hermes_plugin": True}
            outer = json.loads(result)
            outer.pop("structuredContent", None)
            outer["result"] = json.dumps(data, ensure_ascii=False)
            return json.dumps(outer, ensure_ascii=False)
        except Exception:
            logger.exception("glorya: transform_tool_result failed for %s", tool_name)
            return None

    def on_pre_llm_call(self, **_: Any) -> Optional[dict[str, str]]:
        """Remind the model of this chat's Glorya jobs: open questions it can answer with ``respond``
        and recent results it can change with ``refine``. When Glorya isn't connected, say so instead."""
        try:
            server = self.settings().server
            if not self.connected(server):
                return {"context": NOT_CONNECTED.format(server=server)}
            key = self.session().key
            if not key:
                return None
            now = self.clock()
            jobs = [job for job in self.store.recent(session_key=key, limit=5, since=now - 6 * 3600)
                    if not job.terminal or (job.finished_at and now - job.finished_at < CONTEXT_WINDOW_SECONDS)]
            if not jobs:
                return None
            lines = ["[Glorya plugin] Glorya jobs in this chat:"]
            for job in jobs:
                lines.append(f"- job_id {job.job_id}: {render.label(job.kind)}"
                             + (f' "{render.clip(job.title, 60)}"' if job.title else "") + f", {job.status}")
                for q in job.questions():
                    choices = " | ".join(str(c) for c in q.get("choices") or [])
                    lines.append(f"  open question request_id {q.get('request_id')} ({q.get('kind')}): "
                                 f"{render.clip(q.get('question'), 200)}" + (f" Choices: {choices}" if choices else ""))
            lines.append(
                f"If the user's message answers an open question, call mcp__{server}__respond with that job_id, "
                "request_id and the exact choice label (or their own words for input, revise and clarify). "
                f"If they want a change to one of these results, call mcp__{server}__refine with its job_id. "
                "The plugin follows running jobs and posts their updates; don't poll get_job for them.")
            return {"context": "\n".join(lines)[:2500]}
        except Exception:
            logger.exception("glorya: pre_llm_call failed")
            return None

    # -- native tools ---------------------------------------------------------------------------

    def tool_attach(self, args: dict, **_: Any) -> str:
        """Download a finished job's files and return the MEDIA lines that attach them to the reply."""
        job_id = str((args or {}).get("job_id") or "").strip()
        if not job_id:
            return json.dumps({"error": "job_id is required"})
        try:
            limit = max(1, min(8, int((args or {}).get("max_files") or 4)))
        except (TypeError, ValueError):
            limit = 4
        try:
            view = self.glorya().get_job(job_id)
        except GloryaError as error:
            return json.dumps({"error": error.message, "code": error.code, **({"link": error.link()} if error.link() else {})})
        assets = render.assets_of(view)
        if view.get("status") != "completed" or not assets:
            return json.dumps({"job_id": job_id, "status": view.get("status"), "files": [],
                               "note": "Nothing to attach yet." if view.get("status") not in TERMINAL else
                               "This job has no image or video files.", "open_url": view.get("open_url")})
        settings = self.settings()
        files, links = self.fetch(assets, self.data_dir() / "media" / job_id,
                                  settings.attach_max_mb * 1024 * 1024, limit=limit)
        if self.store.get(job_id):
            self.store.set_files(job_id, files)
        return json.dumps({
            "job_id": job_id, "files": files, "links": [a.get("url") for a in links],
            "reply_lines": [f"MEDIA:{f['path']}" for f in files],
            "note": "To attach the files, put each reply_lines entry in your reply exactly as written, on its own "
                    "line. Share links as plain URLs.",
            "open_url": view.get("open_url"),
        }, ensure_ascii=False)

    def tool_jobs(self, args: dict, **_: Any) -> str:
        scope = str((args or {}).get("scope") or "chat")
        key = self.session().key if scope == "chat" else ""
        jobs = self.store.recent(session_key=key, limit=10)
        return json.dumps({"jobs": [
            {"job_id": j.job_id, "kind": j.kind, "title": j.title, "status": j.status, "open_url": j.open_url,
             "questions": j.questions(), "updated_at": int(j.updated_at)} for j in jobs]}, ensure_ascii=False)


ATTACH_SCHEMA = {
    "name": "glorya_attach",
    "description": (
        "Download the finished images or video of a Glorya job and get the MEDIA lines that attach them to your "
        "reply as real files. Use it when the user wants a Glorya result sent into this chat, or in scheduled runs "
        "after get_job says completed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "The job_id a Glorya create tool or refine returned."},
            "max_files": {"type": "integer", "minimum": 1, "maximum": 8, "description": "Default 4."},
        },
        "required": ["job_id"],
    },
}

JOBS_SCHEMA = {
    "name": "glorya_jobs",
    "description": (
        "List the Glorya jobs this Hermes profile follows, newest first, with status and open questions. "
        "scope 'chat' (default) is this chat only; 'all' is every chat."
    ),
    "parameters": {
        "type": "object",
        "properties": {"scope": {"type": "string", "enum": ["chat", "all"]}},
    },
}
