"""Plugin settings (``plugins.entries.glorya.settings``) with validated defaults."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MCP_URL = "https://platform.glorya.ai/mcp"
DOCS_URL = "https://github.com/Glorya-AI/hermes-plugin#readme"
PLUGIN_ID = "glorya"

_SERVER_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


@dataclass(frozen=True)
class Settings:
    server: str = "glorya"
    follow: bool = True
    deliver: str = "attach"
    attach_max_mb: int = 45
    follow_minutes: int = 90

    def tool_name(self, tool: str) -> str:
        """The model-facing name Hermes gives a tool on our MCP server."""
        return f"mcp__{self.server}__{tool}"


def _clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def load(ctx: Any) -> Settings:
    defaults = Settings()

    def get(key: str, default: Any) -> Any:
        try:
            value = ctx.get_config(key, default=default)
        except Exception:
            return default
        return default if value is None else value

    server = str(get("server", defaults.server)).strip()
    deliver = str(get("deliver", defaults.deliver)).strip().lower()
    return Settings(
        server=server if _SERVER_RE.match(server) else defaults.server,
        follow=bool(get("follow", defaults.follow)),
        deliver=deliver if deliver in {"attach", "links"} else defaults.deliver,
        attach_max_mb=_clamp(get("attach_max_mb", defaults.attach_max_mb), 1, 500, defaults.attach_max_mb),
        follow_minutes=_clamp(get("follow_minutes", defaults.follow_minutes), 5, 360, defaults.follow_minutes),
    )
