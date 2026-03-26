"""Unified CLI for WeiLink.

Provides ``admin``, ``mcp``, and ``openapi`` subcommands::

    weilink admin --host 0.0.0.0 -p 8080
    weilink mcp -t sse -p 8000 --admin-port 8080 -d /data/weilink
    weilink openapi -p 8000
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from pathlib import Path
from typing import Any, Literal, cast


def _run_admin(args: argparse.Namespace) -> None:
    """Start the admin panel and block until terminated."""
    from weilink import WeiLink
    from weilink._banner import display_startup_banner

    display_startup_banner(no_banner=args.no_banner)

    kwargs: dict[str, Any] = {}
    if args.base_path:
        kwargs["base_path"] = Path(args.base_path)

    wl = WeiLink(**kwargs)

    # Session summary
    connected = [n for n, s in wl._sessions.items() if s.bot_info]
    if connected:
        print(f"  {len(connected)} session(s) loaded: {', '.join(connected)}")
    else:
        print("  No connected sessions")

    info = wl.start_admin(host=args.host, port=args.port)

    print(f"  Admin panel: {info.url}")
    print(f"  Data: {wl._base_path}")
    print("  Press Ctrl+C to stop.")

    stop = threading.Event()

    def _handle_signal(signum: int, frame: object) -> None:
        print("\nShutting down...")
        stop.set()

    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except ValueError:
        pass  # Not in main thread

    stop.wait()
    wl.close()
    print("Admin panel stopped.")


def _run_mcp(args: argparse.Namespace) -> None:
    """Start the MCP server, optionally with an admin panel."""
    from weilink._banner import display_startup_banner
    from weilink.server.app import run_mcp

    # Skip banner for stdio (stdout is the MCP protocol channel).
    no_banner = args.no_banner or args.transport == "stdio"
    display_startup_banner(no_banner=no_banner)

    base_path = Path(args.base_path) if args.base_path else None

    # Optionally start admin panel in the same process.
    if args.admin_port is not None:
        from weilink.server.app import _init_client

        _init_client(base_path)

        from weilink.server.app import _wl

        if _wl is not None:
            admin_info = _wl.start_admin(host=args.host, port=args.admin_port)
            print(f"WeiLink admin panel running at {admin_info.url}")

    transport_raw = cast(str, args.transport)
    if transport_raw == "http":
        transport_raw = "streamable-http"
    transport = cast(Literal["stdio", "sse", "streamable-http"], transport_raw)
    run_mcp(
        transport=transport,
        host=args.host,
        port=args.port,
        base_path=base_path,
    )


def _run_openapi(args: argparse.Namespace) -> None:
    """Start the OpenAPI server, optionally with an admin panel."""
    from weilink._banner import display_startup_banner
    from weilink.server.app import run_openapi

    display_startup_banner(no_banner=args.no_banner)

    base_path = Path(args.base_path) if args.base_path else None

    # Optionally start admin panel in the same process.
    if args.admin_port is not None:
        from weilink.server.app import _init_client

        _init_client(base_path)

        from weilink.server.app import _wl

        if _wl is not None:
            admin_info = _wl.start_admin(host=args.host, port=args.admin_port)
            print(f"WeiLink admin panel running at {admin_info.url}")

    run_openapi(
        host=args.host,
        port=args.port,
        base_path=base_path,
    )


def main(argv: list[str] | None = None) -> None:
    """Unified WeiLink CLI entry point."""
    from weilink._banner import version_check

    parser = argparse.ArgumentParser(
        prog="weilink",
        description="WeiLink — lightweight WeChat iLink Bot SDK CLI.",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {version_check()}",
        help="show version and check for updates",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── admin subcommand ──────────────────────────────────────────
    admin_parser = subparsers.add_parser(
        "admin",
        help="Start the web admin panel for managing bot sessions.",
    )
    admin_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host address to bind to (default: 127.0.0.1)",
    )
    admin_parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8080,
        help="port number (default: 8080)",
    )
    admin_parser.add_argument(
        "--base-path",
        "-d",
        default=None,
        help="data directory / profile path (default: ~/.weilink/)",
    )
    admin_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging level (default: INFO)",
    )
    admin_parser.add_argument(
        "--no-banner",
        action="store_true",
        default=False,
        help="suppress the ASCII banner on startup",
    )

    # ── openapi subcommand ────────────────────────────────────────
    openapi_parser = subparsers.add_parser(
        "openapi",
        help="Start the OpenAPI (REST) server for tool integration.",
    )
    openapi_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host address to bind to (default: 127.0.0.1)",
    )
    openapi_parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="port number (default: 8000)",
    )
    openapi_parser.add_argument(
        "--base-path",
        "-d",
        default=None,
        help="data directory / profile path (default: ~/.weilink/)",
    )
    openapi_parser.add_argument(
        "--admin-port",
        type=int,
        default=None,
        help="also start admin panel on this port (same host)",
    )
    openapi_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging level (default: INFO)",
    )
    openapi_parser.add_argument(
        "--no-banner",
        action="store_true",
        default=False,
        help="suppress the ASCII banner on startup",
    )

    # ── mcp subcommand ────────────────────────────────────────────
    mcp_parser = subparsers.add_parser(
        "mcp",
        help="Start the MCP server for AI agent integration.",
    )
    mcp_parser.add_argument(
        "--transport",
        "-t",
        default="stdio",
        choices=["stdio", "sse", "streamable-http", "http"],
        help="MCP transport: stdio, sse, streamable-http (or http) (default: stdio)",
    )
    mcp_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host address for SSE/streamable-http (default: 127.0.0.1)",
    )
    mcp_parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="port for SSE/streamable-http (default: 8000)",
    )
    mcp_parser.add_argument(
        "--base-path",
        "-d",
        default=None,
        help="data directory / profile path (default: ~/.weilink/)",
    )
    mcp_parser.add_argument(
        "--admin-port",
        type=int,
        default=None,
        help="also start admin panel on this port (same host)",
    )
    mcp_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging level (default: INFO)",
    )
    mcp_parser.add_argument(
        "--no-banner",
        action="store_true",
        default=False,
        help="suppress the ASCII banner on startup",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.command == "admin":
        _run_admin(args)
    elif args.command == "openapi":
        _run_openapi(args)
    elif args.command == "mcp":
        _run_mcp(args)


if __name__ == "__main__":
    main()
