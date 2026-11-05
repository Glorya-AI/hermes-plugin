"""Calls to the Glorya MCP server through Hermes' own MCP client (``ctx.call_mcp``).

Hermes holds the OAuth token; this module only shapes requests and results. Results arrive as the
tool's JSON text; failures as ``"<message>\\n{"error": "<code>", ...}"`` from the Glorya server.
"""

from __future__ import annotations

import json
from typing import Any, Optional


class GloryaError(Exception):
    """A failed Glorya call: ``code`` is Glorya's error code (or one of ours), ``data`` its details."""

    def __init__(self, code: str, message: str, data: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}

    def link(self) -> Optional[str]:
        for key in ("checkout_url", "billing_url", "open_url"):
            value = self.data.get(key)
            if isinstance(value, str) and value.startswith("https://"):
                return value
        return None


# Codes after which following a job cannot succeed.
FATAL_CODES = frozenset({"job_not_found", "not_allowed", "view_only", "workspace_not_found"})


def parse_error(text: Any) -> GloryaError:
    """Split Glorya's "message, then JSON details" error text; anything else is an upstream error."""
    raw = text if isinstance(text, str) else json.dumps(text) if text is not None else ""
    message, details = raw.strip(), {}
    head, sep, tail = message.rpartition("\n")
    if sep:
        try:
            parsed = json.loads(tail)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            message, details = head.strip(), parsed
    if not details and message.startswith("{"):
        try:
            parsed = json.loads(message)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            details = parsed
            message = str(parsed.get("message") or parsed.get("error") or message)
    code = str(details.pop("error", "") or "upstream_error")
    return GloryaError(code, message or "Glorya returned an error.", details)


def parse_result(envelope: dict[str, Any]) -> dict[str, Any]:
    """The tool's JSON object from a ``ctx.call_mcp`` envelope; raises ``GloryaError`` on failure."""
    if not envelope.get("ok"):
        raise parse_error(envelope.get("error"))
    structured = envelope.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    result = envelope.get("result")
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    raise GloryaError("bad_response", "Glorya sent a reply the plugin could not read.")


def parse_tool_result(result: Any) -> Optional[dict[str, Any]]:
    """The Glorya object inside a model-facing MCP tool result string (``{"result": "<json>"}``), or
    ``None`` when it is an error or not ours."""
    if not isinstance(result, str):
        return None
    try:
        outer = json.loads(result)
    except ValueError:
        return None
    if not isinstance(outer, dict) or "error" in outer:
        return None
    try:
        return parse_result({"ok": True, **outer})
    except GloryaError:
        return None


class Glorya:
    """The MCP tools, by name. Every method returns the tool's JSON object or raises ``GloryaError``."""

    def __init__(self, ctx: Any, server: str):
        self._ctx = ctx
        self.server = server

    def call(self, tool: str, arguments: Optional[dict[str, Any]] = None, timeout: float = 30) -> dict[str, Any]:
        args = {key: value for key, value in (arguments or {}).items() if value not in (None, "", [])}
        try:
            envelope = self._ctx.call_mcp(self.server, tool, args, timeout=timeout)
        except PermissionError:
            raise GloryaError(
                "not_allowed",
                f"The Glorya plugin may not use the '{self.server}' MCP server yet. Run `hermes glorya setup`.",
            ) from None
        except Exception as exc:  # call_mcp is documented not to raise; stay safe if it does
            raise GloryaError("mcp_unavailable", f"Could not reach Glorya: {exc}") from None
        if not isinstance(envelope, dict):
            raise GloryaError("bad_response", "Hermes returned an unexpected MCP result.")
        return parse_result(envelope)

    def get_job(self, job_id: str, wait_seconds: int = 0) -> dict[str, Any]:
        wait = max(0, min(45, int(wait_seconds)))
        return self.call("get_job", {"job_id": job_id, "wait_seconds": wait}, timeout=wait + 25)

    def create(self, kind: str, brief: str, **options: Any) -> dict[str, Any]:
        tool = CREATE_TOOLS[kind]
        return self.call(tool, {"brief": brief, **options}, timeout=60)

    def respond(self, job_id: str, answer: str, request_id: Optional[str] = None) -> dict[str, Any]:
        return self.call("respond", {"job_id": job_id, "answer": answer, "request_id": request_id})

    def refine(self, job_id: str, instruction: str) -> dict[str, Any]:
        return self.call("refine", {"job_id": job_id, "instruction": instruction}, timeout=60)

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self.call("cancel_job", {"job_id": job_id})

    def publish(self, job_id: str, slug: Optional[str] = None) -> dict[str, Any]:
        return self.call("publish_site", {"job_id": job_id, "slug": slug}, timeout=60)

    def brand(self) -> dict[str, Any]:
        return self.call("get_brand")

    def credits(self) -> dict[str, Any]:
        return self.call("get_credits")

    def integrations(self) -> dict[str, Any]:
        return self.call("get_integrations")

    def campaigns(self, **filters: Any) -> dict[str, Any]:
        return self.call("list_campaigns", filters)

    def sites(self, **filters: Any) -> dict[str, Any]:
        return self.call("list_sites", filters)

    def formats(self) -> dict[str, Any]:
        return self.call("list_video_formats")


CREATE_TOOLS = {
    "image_ad": "create_image_ad",
    "video_ad": "create_video_ad",
    "landing_page": "create_landing_page",
    "website": "create_website",
    "campaign": "create_campaign",
}

# Tools whose result starts (or restarts) work on a job the plugin can follow.
JOB_TOOLS = frozenset({*CREATE_TOOLS.values(), "refine", "respond", "publish_site"})
