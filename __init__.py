"""Glorya for Hermes: on-brand image ads, video ads, landing pages and websites, followed in your chat.

The Glorya MCP server (https://platform.glorya.ai/mcp, OAuth through Hermes) does the work. This
plugin follows the jobs it starts in the background, posts progress, questions and finished files in
the chat that asked, and adds ``/glorya``, ``hermes glorya setup``, two native tools, a skill and
scheduled blueprints.
"""

from __future__ import annotations

from pathlib import Path

from . import blueprints, cli
from .commands import Commands
from .core import ATTACH_SCHEMA, JOBS_SCHEMA, GloryaPlugin

_HERE = Path(__file__).parent
TOOLSET = "glorya-plugin"


def register(ctx) -> None:
    plugin = GloryaPlugin(ctx)
    ctx.register_hook("pre_tool_call", plugin.on_pre_tool_call)
    ctx.register_hook("transform_tool_result", plugin.on_transform_tool_result)
    ctx.register_hook("pre_llm_call", plugin.on_pre_llm_call)
    # Not "glorya": a plugin toolset with the MCP server's name hides that server's mcp__glorya__ tools.
    ctx.register_tool(name="glorya_attach", toolset=TOOLSET, schema=ATTACH_SCHEMA, handler=plugin.tool_attach)
    ctx.register_tool(name="glorya_jobs", toolset=TOOLSET, schema=JOBS_SCHEMA, handler=plugin.tool_jobs)
    ctx.register_command("glorya", Commands(plugin), description="Glorya: make on-brand ads and pages, follow jobs",
                         args_hint="image|video|page|site <brief> · jobs · answer · refine · publish · cancel")
    ctx.register_cli_command(name="glorya", help="Set up and check the Glorya plugin",
                             setup_fn=cli.setup_argparse, handler_fn=cli.handle)
    ctx.register_skill("glorya", _HERE / "skills" / "glorya" / "SKILL.md",
                       description="Make on-brand image ads, video ads, landing pages and websites with Glorya.")
    blueprints.register(ctx)
