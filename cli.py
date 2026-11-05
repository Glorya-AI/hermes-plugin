"""``hermes glorya setup|status`` — add the Glorya MCP server and grant this plugin what it needs.

Setup only writes config through Hermes' own public commands (``hermes plugins enable``,
``hermes config set``), each after the user says yes. The running gateway picks the changes up
by itself, so nothing restarts. Signing in happens in chat: the plugin has the agent open Hermes'
own connection flow (``manage_connections`` authorize), which keeps a saved sign-in.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from typing import Any, Callable, Optional

from .settings import DOCS_URL, MCP_URL, PLUGIN_ID

Runner = Callable[[list[str]], int]


def _load_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config_readonly
        return load_config_readonly() or {}
    except Exception:
        return {}


def _hermes() -> list[str]:
    exe = shutil.which("hermes")
    return [exe] if exe else [sys.executable, "-m", "hermes_cli.main"]


def _run(argv: list[str]) -> int:
    return subprocess.call(argv)


def _in_agent_turn() -> bool:
    """Hermes sets the session key for commands its agent runs."""
    return bool(os.environ.get("HERMES_SESSION_KEY"))


def _entry(config: dict[str, Any]) -> dict[str, Any]:
    entries = ((config.get("plugins") or {}).get("entries") or {})
    entry = entries.get(PLUGIN_ID)
    return entry if isinstance(entry, dict) else {}


def server_name(config: dict[str, Any]) -> str:
    return str(((_entry(config).get("settings") or {}).get("server")) or "glorya")


def check(config: dict[str, Any]) -> list[tuple[str, bool, list[str]]]:
    """``(name, ok, fix commands)`` for each thing the plugin needs."""
    entry = _entry(config)
    server = server_name(config)
    servers = config.get("mcp_servers") or {}
    spec = servers.get(server) if isinstance(servers, dict) else None
    allow = entry.get("mcp_allowlist") if isinstance(entry.get("mcp_allowlist"), list) else []
    enabled = PLUGIN_ID in ((config.get("plugins") or {}).get("enabled") or [])
    return [
        ("plugin enabled", enabled, [f"hermes plugins enable {PLUGIN_ID}"]),
        (f"MCP server '{server}' -> {MCP_URL}", isinstance(spec, dict) and str(spec.get("url", "")).rstrip("/") == MCP_URL
         and spec.get("auth") == "oauth",
         [f"hermes config set mcp_servers.{server}.url {MCP_URL}", f"hermes config set mcp_servers.{server}.auth oauth"]),
        (f"plugin may call '{server}'", server in allow,
         [f"hermes config set plugins.entries.{PLUGIN_ID}.mcp_allowlist '{json.dumps([server])}'"]),
        ("send finished files as attachments", entry.get("allow_gateway_injection") is True,
         [f"hermes config set plugins.entries.{PLUGIN_ID}.allow_gateway_injection true"]),
    ]


def _ask(question: str, default: bool, read: Callable[[str], str]) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = read(question + suffix).strip().lower()
    except EOFError:
        return False
    return default if not answer else answer in ("y", "yes")


DONE = ("\nDone. Nothing to restart. In any Hermes chat, ask for an ad, e.g. \"make an image ad for our bestseller\".\n"
        "The first time, Hermes shows a Glorya sign-in link: open it on this computer and sign in.")


def setup(*, interactive: Optional[bool] = None, run: Runner = _run, read: Callable[[str], str] = input,
          load: Callable[[], dict[str, Any]] = _load_config, out: Callable[[str], None] = print,
          hermes: Optional[list[str]] = None, in_agent: Callable[[], bool] = _in_agent_turn) -> int:
    if in_agent():
        out("Run `hermes glorya setup` in your own terminal: it asks you before changing your config.")
        return 1
    interactive = sys.stdin.isatty() if interactive is None else interactive
    hermes = hermes or _hermes()
    steps = check(load())
    out("Glorya for Hermes: on-brand image ads, video ads, landing pages and websites.")
    out("You need a Glorya account with an active plan (https://glorya.ai).\n")
    if not interactive:
        for name, ok, fixes in steps:
            out(f"{'✓' if ok else '•'} {name}" + "".join(f"\n    {fix}" for fix in ([] if ok else fixes)))
        out(f"Docs: {DOCS_URL}")
        return 0
    prompts = [
        "Enable the Glorya plugin?",
        f"Add the Glorya MCP server ({MCP_URL})? You sign in with your Glorya account in chat.",
        "Let the Glorya plugin use that server to follow your jobs?",
        "Send finished videos and images into the chat as attachments? When a job finishes, the plugin starts one "
        "short agent turn in that chat to post the files.",
    ]
    for (name, ok, fixes), prompt in zip(steps, prompts):
        if ok:
            out(f"✓ {name}")
        elif not _ask(prompt, True, read):
            out(f"• skipped: {name}")
        elif all(run(hermes + shlex.split(fix)[1:]) == 0 for fix in fixes):
            out(f"✓ {name}")
        else:
            out(f"✗ {name} (failed; run: {' && '.join(fixes)})")
    out(DONE)
    out(f"Docs: {DOCS_URL}")
    return 0


def status(*, load: Callable[[], dict[str, Any]] = _load_config, out: Callable[[str], None] = print) -> int:
    config = load()
    steps = check(config)
    for name, ok, fixes in steps:
        out(f"{'✓' if ok else '✗'} {name}" + "".join(f"\n    fix: {fix}" for fix in ([] if ok else fixes)))
    out(f"Sign-in: run `hermes mcp test {server_name(config)}`, or just ask Hermes for an ad.")
    return 0 if all(ok for _, ok, _ in steps[:3]) else 1


def setup_argparse(parser: Any) -> None:
    subs = parser.add_subparsers(dest="glorya_command")
    subs.add_parser("setup", help="Add Glorya and grant the plugin what it needs")
    subs.add_parser("status", help="Show what is set up")
    parser.set_defaults(func=handle)


def handle(args: Any) -> int:
    command = getattr(args, "glorya_command", None)
    if command == "setup":
        return setup()
    if command == "status":
        return status()
    print("Usage: hermes glorya setup | status")
    return 0
