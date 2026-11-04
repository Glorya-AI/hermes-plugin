"""``hermes glorya setup|status`` — connect the Glorya MCP server and grant this plugin what it needs.

Setup only runs Hermes' own public commands (``hermes mcp add|login``, ``hermes config set``), each
after the user says yes. Without a terminal it prints the commands instead.
"""

from __future__ import annotations

import json
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


def _entry(config: dict[str, Any]) -> dict[str, Any]:
    entries = ((config.get("plugins") or {}).get("entries") or {})
    entry = entries.get(PLUGIN_ID)
    return entry if isinstance(entry, dict) else {}


def server_name(config: dict[str, Any]) -> str:
    return str(((_entry(config).get("settings") or {}).get("server")) or "glorya")


def check(config: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """``(name, ok, how to fix)`` for each thing the plugin needs."""
    entry = _entry(config)
    server = server_name(config)
    servers = config.get("mcp_servers") or {}
    spec = servers.get(server) if isinstance(servers, dict) else None
    allow = entry.get("mcp_allowlist") if isinstance(entry.get("mcp_allowlist"), list) else []
    enabled = PLUGIN_ID in ((config.get("plugins") or {}).get("enabled") or [])
    return [
        ("plugin enabled", enabled, f"hermes plugins enable {PLUGIN_ID}"),
        (f"MCP server '{server}' -> {MCP_URL}", isinstance(spec, dict) and str(spec.get("url", "")).rstrip("/") == MCP_URL
         and spec.get("auth") == "oauth", f"hermes mcp add {server} --url {MCP_URL} --auth oauth"),
        (f"plugin may call '{server}'", server in allow,
         f"hermes config set plugins.entries.{PLUGIN_ID}.mcp_allowlist '{json.dumps([server])}'"),
        ("send finished files as attachments", entry.get("allow_gateway_injection") is True,
         f"hermes config set plugins.entries.{PLUGIN_ID}.allow_gateway_injection true"),
    ]


def _ask(question: str, default: bool, read: Callable[[str], str]) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = read(question + suffix).strip().lower()
    except EOFError:
        return False
    return default if not answer else answer in ("y", "yes")


def setup(*, interactive: Optional[bool] = None, run: Runner = _run, read: Callable[[str], str] = input,
          load: Callable[[], dict[str, Any]] = _load_config, out: Callable[[str], None] = print,
          hermes: Optional[list[str]] = None) -> int:
    interactive = sys.stdin.isatty() if interactive is None else interactive
    hermes = hermes or _hermes()
    config = load()
    steps = check(config)
    server = server_name(config)
    out("Glorya for Hermes: on-brand image ads, video ads, landing pages and websites.")
    out("You need a Glorya account with an active plan (https://glorya.ai).\n")
    if not interactive:
        for name, ok, fix in steps:
            out(f"{'✓' if ok else '•'} {name}" + ("" if ok else f"\n    {fix}"))
        out(f"    hermes mcp login {server}\nThen restart: hermes gateway restart\nDocs: {DOCS_URL}")
        return 0
    prompts = [
        "Enable the Glorya plugin?",
        f"Add the Glorya MCP server ({MCP_URL}, sign-in with your Glorya account)?",
        f"Let the Glorya plugin use the '{server}' MCP server to follow your jobs?",
        "Send finished videos and images into the chat as attachments? When a job finishes, the plugin starts one "
        "short agent turn in that chat to post the files.",
    ]
    for (name, ok, fix), prompt in zip(steps, prompts):
        if ok:
            out(f"✓ {name}")
            continue
        if _ask(prompt, True, read):
            code = run(hermes + _argv(fix))
            out(f"{'✓' if code == 0 else '✗'} {name}" + ("" if code == 0 else f" (failed; run: {fix})"))
        else:
            out(f"• skipped: {name}")
    if _ask("Sign in to Glorya now? A browser window opens.", True, read):
        code = run(hermes + ["mcp", "login", server])
        out("✓ signed in" if code == 0 else f"✗ sign-in did not finish; run: hermes mcp login {server}")
    out("\nRestart Hermes so the plugin and tools load: hermes gateway restart")
    out("Then try: /glorya image summer sale for our bestseller   (or just ask for an ad)")
    out(f"Docs: {DOCS_URL}")
    return 0


def _argv(fix: str) -> list[str]:
    """``hermes …`` fix line -> argv after the executable (quotes respected)."""
    import shlex
    return shlex.split(fix)[1:]


def status(*, load: Callable[[], dict[str, Any]] = _load_config, out: Callable[[str], None] = print) -> int:
    config = load()
    steps = check(config)
    for name, ok, fix in steps:
        out(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    fix: {fix}"))
    out(f"Sign-in: run `hermes mcp test {server_name(config)}` to check the connection.")
    return 0 if all(ok for _, ok, _ in steps[:3]) else 1


def setup_argparse(parser: Any) -> None:
    subs = parser.add_subparsers(dest="glorya_command")
    subs.add_parser("setup", help="Connect Glorya and grant the plugin what it needs")
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
