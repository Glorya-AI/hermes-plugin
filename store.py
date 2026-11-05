"""Durable record of the Glorya jobs this profile follows (SQLite in the plugin's data dir).

The Desktop backend reads the same file, so every write is a short transaction under one lock.
"""

# No `from __future__ import annotations`: the Desktop host loads this file by path, and @dataclass
# would then look string annotations up in sys.modules, where this module isn't.
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

TERMINAL = frozenset({"completed", "failed", "cancelled"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'running',
  open_url TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'agent',
  session_key TEXT NOT NULL DEFAULT '',
  session_id TEXT NOT NULL DEFAULT '',
  platform TEXT NOT NULL DEFAULT '',
  view TEXT NOT NULL DEFAULT '{}',
  asked TEXT NOT NULL DEFAULT '[]',
  delivered TEXT NOT NULL DEFAULT '[]',
  files TEXT NOT NULL DEFAULT '[]',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  finished_at REAL
);
CREATE INDEX IF NOT EXISTS jobs_session ON jobs (session_key, updated_at);
"""


@dataclass
class Job:
    job_id: str
    kind: str = ""
    title: str = ""
    status: str = "running"
    open_url: str = ""
    source: str = "agent"
    session_key: str = ""
    session_id: str = ""
    platform: str = ""
    view: dict[str, Any] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)
    delivered: list[str] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    finished_at: Optional[float] = None

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL

    @property
    def short_id(self) -> str:
        return self.job_id[:8]

    def questions(self) -> list[dict[str, Any]]:
        if self.status != "needs_input":
            return []
        return [q for q in self.view.get("questions") or [] if isinstance(q, dict)]

    def to_public(self) -> dict[str, Any]:
        """What the Desktop pane and ``glorya_jobs`` show: no session routing data."""
        site = self.view.get("site") if isinstance(self.view.get("site"), dict) else None
        return {
            "job_id": self.job_id, "kind": self.kind, "title": self.title, "status": self.status,
            "open_url": self.open_url, "progress": _clip(self.view.get("progress"), 400),
            "assets": [a for a in self.view.get("assets") or [] if isinstance(a, dict)][:8],
            "questions": self.questions(), "site": site, "files": self.files,
            "source": self.source, "platform": self.platform, "session_id": self.session_id,
            "created_at": self.created_at, "updated_at": self.updated_at, "finished_at": self.finished_at,
        }


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


_JSON_FIELDS = ("view", "asked", "delivered", "files")
_COLUMNS = ("job_id", "kind", "title", "status", "open_url", "source", "session_key", "session_id", "platform",
            *_JSON_FIELDS, "created_at", "updated_at", "finished_at")


class Store:
    def __init__(self, connect: Callable[[], sqlite3.Connection], clock: Callable[[], float] = time.time):
        self._connect = connect
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._clock = clock

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
            self._conn.executescript(_SCHEMA)
        return self._conn

    @staticmethod
    def _row(row: Iterable[Any]) -> Job:
        values = dict(zip(_COLUMNS, row))
        for key in _JSON_FIELDS:
            try:
                values[key] = json.loads(values[key] or "null") or ({} if key == "view" else [])
            except ValueError:
                values[key] = {} if key == "view" else []
        return Job(**values)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            row = self._db().execute(f"SELECT {', '.join(_COLUMNS)} FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def find(self, ref: str, session_key: str = "") -> Optional[Job]:
        """A job by full id or id prefix (8+ chars), preferring this chat's jobs."""
        ref = (ref or "").strip()
        if not ref:
            jobs = self.recent(session_key=session_key, limit=1)
            return jobs[0] if jobs else None
        exact = self.get(ref)
        if exact or len(ref) < 6:
            return exact
        with self._lock:
            rows = self._db().execute(
                f"SELECT {', '.join(_COLUMNS)} FROM jobs WHERE job_id LIKE ? ORDER BY (session_key = ?) DESC, "
                "updated_at DESC LIMIT 2", (ref.replace("%", "") + "%", session_key)).fetchall()
        return self._row(rows[0]) if len(rows) == 1 else None

    def recent(self, session_key: str = "", limit: int = 10, since: Optional[float] = None) -> list[Job]:
        clauses, params = [], []
        if session_key:
            clauses.append("session_key = ?")
            params.append(session_key)
        if since is not None:
            clauses.append("updated_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db().execute(
                f"SELECT {', '.join(_COLUMNS)} FROM jobs {where} ORDER BY updated_at DESC LIMIT ?",
                (*params, max(1, min(100, limit)))).fetchall()
        return [self._row(row) for row in rows]

    def track(self, job_id: str, *, kind: str = "", title: str = "", status: str = "running", open_url: str = "",
              source: str = "agent", session_key: str = "", platform: str = "") -> Job:
        """Insert a job, or reopen it (a refine or an answer restarts work on the same id)."""
        now = self._clock()
        with self._lock:
            db = self._db()
            db.execute(
                "INSERT INTO jobs (job_id, kind, title, status, open_url, source, session_key, platform, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(job_id) DO UPDATE SET "
                "kind = COALESCE(NULLIF(excluded.kind, ''), kind), title = COALESCE(NULLIF(excluded.title, ''), title), "
                "status = excluded.status, open_url = COALESCE(NULLIF(excluded.open_url, ''), open_url), "
                "session_key = COALESCE(NULLIF(excluded.session_key, ''), session_key), "
                "platform = COALESCE(NULLIF(excluded.platform, ''), platform), updated_at = excluded.updated_at, "
                "finished_at = NULL",
                (job_id, kind, title, status, open_url, source, session_key, platform, now, now))
            db.commit()
        job = self.get(job_id)
        assert job is not None
        return job

    def save_view(self, job_id: str, view: dict[str, Any]) -> Optional[Job]:
        status = str(view.get("status") or "running")
        now = self._clock()
        with self._lock:
            db = self._db()
            db.execute(
                "UPDATE jobs SET view = ?, status = ?, kind = COALESCE(NULLIF(?, ''), kind), "
                "title = COALESCE(NULLIF(?, ''), title), open_url = COALESCE(NULLIF(?, ''), open_url), "
                "updated_at = ?, finished_at = CASE WHEN ? THEN COALESCE(finished_at, ?) ELSE NULL END "
                "WHERE job_id = ?",
                (json.dumps(view, ensure_ascii=False), status, str(view.get("kind") or ""),
                 str(view.get("title") or ""), str(view.get("open_url") or ""), now,
                 status in TERMINAL, now, job_id))
            db.commit()
        return self.get(job_id)

    def add_marks(self, job_id: str, column: str, values: Iterable[str]) -> None:
        """Remember question ids already posted (``asked``) or asset ids already sent (``delivered``)."""
        if column not in {"asked", "delivered"}:
            raise ValueError(column)
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return
            merged = list(dict.fromkeys([*getattr(job, column), *values]))[-200:]
            db = self._db()
            db.execute(f"UPDATE jobs SET {column} = ? WHERE job_id = ?", (json.dumps(merged), job_id))
            db.commit()

    def set_session_id(self, job_id: str, session_id: str) -> None:
        if not session_id:
            return
        with self._lock:
            db = self._db()
            db.execute("UPDATE jobs SET session_id = ? WHERE job_id = ?", (session_id, job_id))
            db.commit()

    def set_files(self, job_id: str, files: list[dict[str, Any]]) -> None:
        with self._lock:
            db = self._db()
            db.execute("UPDATE jobs SET files = ? WHERE job_id = ?", (json.dumps(files, ensure_ascii=False), job_id))
            db.commit()

    def prune(self, keep_days: int = 30) -> list[str]:
        """Forget finished jobs older than ``keep_days``; returns their ids (their files can go too)."""
        cutoff = self._clock() - keep_days * 86400
        with self._lock:
            db = self._db()
            ids = [row[0] for row in db.execute(
                "SELECT job_id FROM jobs WHERE updated_at < ? AND status IN ('completed','failed','cancelled')",
                (cutoff,)).fetchall()]
            db.executemany("DELETE FROM jobs WHERE job_id = ?", [(job_id,) for job_id in ids])
            db.commit()
        return ids
