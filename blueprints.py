"""Automation Blueprints: scheduled Glorya runs delivered to a chat (``/blueprint glorya:…``).

Scheduled runs have no live chat, so the plugin doesn't follow them: the prompt has the agent wait
with ``get_job`` and attach the files with ``glorya_attach``; cron delivers the final reply.
"""

from __future__ import annotations

from typing import Any

_DAY = {"name": "day", "type": "enum", "label": "Which day?", "default": "monday",
        "options": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}
_TIME = {"name": "time", "type": "time", "label": "What time?", "default": "09:00"}
_DELIVER = {"name": "deliver", "type": "enum", "label": "Where to deliver?", "default": "origin",
            "options": ["origin", "local"], "strict": False}

_WAIT_AND_ATTACH = (
    "Glorya finishes on its own: don't set review. Call get_job with wait_seconds 30 for each job until its status "
    "is completed or failed. Then call glorya_attach for each completed job and reply with one short line per "
    "result followed by its MEDIA lines exactly as glorya_attach returns them, plus the Glorya link. If a tool says "
    "plan_required, no_credits or setting_up, reply with its message and link instead."
)


def register(ctx: Any) -> None:
    server = "glorya"
    try:
        server = str(ctx.get_config("server", default="glorya") or "glorya")
    except Exception:
        pass
    ctx.register_automation_blueprint(
        "weekly-image-ads",
        title="Weekly on-brand image ads",
        description="Every week, Glorya makes fresh image ads for your brand and posts them here.",
        category="marketing",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            f"Use the Glorya MCP tools (mcp__{server}__*) with the default brand. Start {{count}} separate image ads "
            f"with create_image_ad, one call each, each with a different angle on this theme: {{theme}}. "
            + _WAIT_AND_ATTACH
        ),
        slots=[
            {"name": "theme", "type": "text", "label": "What should the ads be about?",
             "default": "our bestselling product and why customers love it"},
            {"name": "count", "type": "enum", "label": "How many ads?", "default": "2", "options": ["1", "2", "3"]},
            _DAY, _TIME, _DELIVER,
        ],
        tags=["marketing", "ads", "weekly", "glorya"],
    )
    ctx.register_automation_blueprint(
        "weekly-video-ad",
        title="Weekly on-brand video ad",
        description="Every week, Glorya makes a new video ad for your brand in the style you pick and posts it here.",
        category="marketing",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            f"Use the Glorya MCP tools (mcp__{server}__*) with the default brand. Start one video ad with "
            "create_video_ad, brief: {theme}. Use format {format} unless it is 'any'; then leave format out. "
            + _WAIT_AND_ATTACH
        ),
        slots=[
            {"name": "theme", "type": "text", "label": "What should the video be about?",
             "default": "this week's best offer"},
            {"name": "format", "type": "enum", "label": "Video style", "default": "any", "strict": False,
             "options": ["any", "ugc", "launch_video", "street_interview", "tv_spot", "stop_motion", "claymation"]},
            _DAY, _TIME, _DELIVER,
        ],
        tags=["marketing", "video", "weekly", "glorya"],
    )
