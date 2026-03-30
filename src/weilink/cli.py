"""Unified CLI for WeiLink.

Provides subcommands for bot interaction and server management::

    weilink login
    weilink status
    weilink recv --timeout 5
    weilink send USER_ID --text "hello"
    weilink admin --host 0.0.0.0 -p 8080
    weilink mcp -t sse -p 8000 --admin-port 8080 -d /data/weilink
    weilink openapi -p 8000
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Any, Literal, cast


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_client(args: argparse.Namespace) -> Any:
    """Create a WeiLink client from CLI args."""
    from weilink import WeiLink

    kwargs: dict[str, Any] = {"message_store": True}
    if getattr(args, "base_path", None):
        kwargs["base_path"] = Path(args.base_path)
    return WeiLink(**kwargs)


def _json_flag(args: argparse.Namespace) -> bool:
    """Check if --json output is requested."""
    return getattr(args, "json", False)


# ------------------------------------------------------------------
# Bot interaction commands
# ------------------------------------------------------------------


def _run_login(args: argparse.Namespace) -> None:
    """Interactive QR code login."""
    wl = _make_client(args)
    name = getattr(args, "session_name", None) or None
    try:
        bot_info = wl.login(name=name, force=args.force)
    except Exception as e:
        if _json_flag(args):
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Login failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        wl.close()

    if _json_flag(args):
        print(
            json.dumps(
                {
                    "success": True,
                    "bot_id": bot_info.bot_id,
                    "user_id": bot_info.user_id,
                    "session": name or "default",
                }
            )
        )
    else:
        print("Login successful!")
        print(f"  Bot ID:  {bot_info.bot_id}")
        print(f"  User ID: {bot_info.user_id}")
        print(f"  Session: {name or 'default'}")


def _run_logout(args: argparse.Namespace) -> None:
    """Logout a session."""
    wl = _make_client(args)
    name = getattr(args, "session_name", None) or None
    try:
        wl.logout(name=name)
    except Exception as e:
        if _json_flag(args):
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Logout failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        wl.close()

    display_name = name or "default"
    if _json_flag(args):
        print(json.dumps({"success": True, "session": display_name}))
    else:
        print(f"Session '{display_name}' logged out.")


def _run_status(args: argparse.Namespace) -> None:
    """Show session status."""
    wl = _make_client(args)
    sessions_data = []
    for sname, session in wl.sessions.items():
        sessions_data.append(
            {
                "name": sname,
                "bot_id": session.bot_id,
                "user_id": session.user_id,
                "connected": session.is_connected,
                "default": session.is_default,
            }
        )
    wl.close()

    if _json_flag(args):
        print(json.dumps(sessions_data))
    else:
        if not sessions_data:
            print("No sessions found.")
            return
        for s in sessions_data:
            marker = "*" if s["default"] else " "
            status = "connected" if s["connected"] else "disconnected"
            line = f"  {marker} {s['name']}: {status}"
            if s["bot_id"]:
                line += f"  (bot: {s['bot_id']})"
            print(line)


def _run_recv(args: argparse.Namespace) -> None:
    """Receive messages."""
    wl = _make_client(args)
    try:
        messages = wl.recv(timeout=args.timeout)
    except Exception as e:
        if _json_flag(args):
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Receive failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        wl.close()

    if _json_flag(args):
        print(json.dumps([m.to_dict() for m in messages]))
    else:
        if not messages:
            print("No new messages.")
            return
        for msg in messages:
            ts = msg.timestamp // 1000 if msg.timestamp else 0
            from datetime import datetime, timezone

            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            line = f"  [{dt}] {msg.from_user} ({msg.msg_type.name})"
            if msg.text:
                line += f": {msg.text}"
            print(line)
        print(f"\n  {len(messages)} message(s) received.")


def _run_send(args: argparse.Namespace) -> None:
    """Send a message."""
    wl = _make_client(args)
    kwargs: dict[str, Any] = {}
    if args.text:
        kwargs["text"] = args.text
    if args.image:
        kwargs["image"] = Path(args.image).read_bytes()
    if args.file:
        p = Path(args.file)
        kwargs["file"] = p.read_bytes()
        kwargs["file_name"] = args.file_name or p.name
    if args.video:
        kwargs["video"] = Path(args.video).read_bytes()
    if args.voice:
        kwargs["voice"] = Path(args.voice).read_bytes()

    if not kwargs:
        print(
            "Error: at least one of --text, --image, --file, --video, --voice is required.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        result = wl.send(args.to, **kwargs)
    except Exception as e:
        if _json_flag(args):
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Send failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        wl.close()

    if _json_flag(args):
        print(json.dumps({"success": result.success}))
    else:
        if result.success:
            print("Message sent.")
        else:
            print("Send returned failure.")


def _run_download(args: argparse.Namespace) -> None:
    """Download media from a message."""
    wl = _make_client(args)
    store = wl._message_store
    if store is None:
        msg = "Message store not enabled. Use --base-path or set message_store=True."
        if _json_flag(args):
            print(json.dumps({"error": msg}))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        wl.close()
        sys.exit(1)

    try:
        msg_id = int(args.message_id)
    except ValueError:
        err = f"Invalid message_id: {args.message_id}"
        if _json_flag(args):
            print(json.dumps({"error": err}))
        else:
            print(f"Error: {err}", file=sys.stderr)
        wl.close()
        sys.exit(1)

    msg = store.get_by_id(msg_id)
    if msg is None:
        err = f"Message {msg_id} not found in store."
        if _json_flag(args):
            print(json.dumps({"error": err}))
        else:
            print(f"Error: {err}", file=sys.stderr)
        wl.close()
        sys.exit(1)

    try:
        data = wl.download(msg)
    except Exception as e:
        if _json_flag(args):
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Download failed: {e}", file=sys.stderr)
        wl.close()
        sys.exit(1)

    out_dir = (
        Path(args.output) if args.output else Path.home() / ".weilink" / "downloads"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    # Derive filename
    from weilink.models import MessageType

    ext_map = {
        MessageType.IMAGE: ".jpg",
        MessageType.VOICE: ".amr",
        MessageType.VIDEO: ".mp4",
    }
    if msg.file and msg.file.file_name:
        name = msg.file.file_name
    else:
        name = f"{msg.message_id}{ext_map.get(msg.msg_type, '.bin')}"

    out_path = out_dir / name
    out_path.write_bytes(data)
    wl.close()

    if _json_flag(args):
        print(json.dumps({"path": str(out_path), "size": len(data)}))
    else:
        print(f"Saved to {out_path} ({len(data)} bytes)")


def _run_history(args: argparse.Namespace) -> None:
    """Query message history."""
    wl = _make_client(args)
    store = wl._message_store
    if store is None:
        msg = "Message store not enabled."
        if _json_flag(args):
            print(json.dumps({"error": msg}))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        wl.close()
        sys.exit(1)

    from weilink.models import MessageType

    kwargs: dict[str, Any] = {}
    if args.user:
        kwargs["user_id"] = args.user
    if args.bot:
        kwargs["bot_id"] = args.bot
    if args.type:
        try:
            kwargs["msg_type"] = MessageType[args.type.upper()].value
        except KeyError:
            err = f"Unknown message type: {args.type}"
            if _json_flag(args):
                print(json.dumps({"error": err}))
            else:
                print(f"Error: {err}", file=sys.stderr)
            wl.close()
            sys.exit(1)
    if args.direction:
        d = args.direction.lower()
        if d == "received":
            kwargs["direction"] = 1
        elif d == "sent":
            kwargs["direction"] = 2
    if args.since:
        from weilink.server.app import _parse_time

        ts = _parse_time(args.since)
        if ts is not None:
            kwargs["since_ms"] = ts
    if args.until:
        from weilink.server.app import _parse_time

        ts = _parse_time(args.until)
        if ts is not None:
            kwargs["until_ms"] = ts
    if args.text:
        kwargs["text_contains"] = args.text

    total = store.count(**kwargs)
    messages = store.query(**kwargs, limit=args.limit, offset=args.offset)
    wl.close()

    if _json_flag(args):
        print(
            json.dumps(
                {
                    "messages": messages,
                    "total": total,
                    "limit": args.limit,
                    "offset": args.offset,
                }
            )
        )
    else:
        if not messages:
            print("No messages found.")
            return
        for m in messages:
            direction = m.get("direction", "?")
            ts_str = m.get("timestamp", "")
            text = m.get("text", "")
            user = m.get("from_user", "")
            mtype = m.get("msg_type", "?")
            line = f"  [{ts_str}] {direction:>8s} {user} ({mtype})"
            if text:
                line += f": {text[:80]}"
            print(line)
        print(f"\n  Showing {len(messages)} of {total} message(s).")


def _run_sessions(args: argparse.Namespace) -> None:
    """Session management: list, rename, set-default."""
    sub = getattr(args, "sessions_command", None)

    if sub == "rename":
        wl = _make_client(args)
        try:
            wl.rename_session(args.old_name, args.new_name)
        except Exception as e:
            if _json_flag(args):
                print(json.dumps({"error": str(e)}))
            else:
                print(f"Rename failed: {e}", file=sys.stderr)
            wl.close()
            sys.exit(1)
        wl.close()
        if _json_flag(args):
            print(
                json.dumps(
                    {
                        "success": True,
                        "old_name": args.old_name,
                        "new_name": args.new_name,
                    }
                )
            )
        else:
            print(f"Session '{args.old_name}' renamed to '{args.new_name}'.")

    elif sub == "default":
        wl = _make_client(args)
        try:
            wl.set_default(args.session_name)
        except Exception as e:
            if _json_flag(args):
                print(json.dumps({"error": str(e)}))
            else:
                print(f"Set default failed: {e}", file=sys.stderr)
            wl.close()
            sys.exit(1)
        wl.close()
        if _json_flag(args):
            print(json.dumps({"success": True, "default_session": args.session_name}))
        else:
            print(f"Default session set to '{args.session_name}'.")

    else:
        # Default: list sessions (same as `weilink status`)
        _run_status(args)


# ------------------------------------------------------------------
# Server commands
# ------------------------------------------------------------------


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


def _run_migrate(args: argparse.Namespace) -> None:
    """Run credential migration from another tool."""
    from pathlib import Path

    if args.migrate_source == "openclaw":
        from weilink.migrate import migrate_openclaw

        source = Path(args.source or "~/.openclaw").expanduser()
        target = Path(args.base_path or "~/.weilink").expanduser()

        if args.dry_run:
            print("[dry-run] No files will be written.\n")

        print(f"  Source: {source}")
        print(f"  Target: {target}\n")

        results = migrate_openclaw(source, target, dry_run=args.dry_run)

        migrated = skipped = errors = 0
        for r in results:
            if r.status == "migrated":
                migrated += 1
                tag = "[dry-run] " if args.dry_run else ""
                print(f"  + {tag}{r.account_id} -> {r.session_name}")
            elif r.status == "skipped":
                skipped += 1
                print(f"  - {r.account_id} (skipped: already exists)")
            else:
                errors += 1
                print(f"  ! {r.detail}")

        print()
        parts = []
        if migrated:
            parts.append(f"{migrated} migrated")
        if skipped:
            parts.append(f"{skipped} skipped")
        if errors:
            parts.append(f"{errors} error(s)")
        print(f"  Done: {', '.join(parts) or 'nothing to do'}.")


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
        epilog=(
            "bot commands:\n"
            "  login       Login via QR code scan\n"
            "  logout      Log out a session\n"
            "  status      Show session connection status\n"
            "  recv        Receive messages\n"
            "  send        Send a message\n"
            "  download    Download media from a message\n"
            "  history     Query message history\n"
            "  sessions    Session management (list/rename/default)\n"
            "\n"
            "server commands:\n"
            "  admin       Start the web admin panel\n"
            "  mcp         Start the MCP server\n"
            "  openapi     Start the OpenAPI (REST) server\n"
            "\n"
            "other commands:\n"
            "  migrate     Migrate credentials from another tool"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {version_check()}",
        help="show version and check for updates",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Shared option helpers
    def _add_base_path(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--base-path",
            "-d",
            default=None,
            help="data directory / profile path (default: ~/.weilink/)",
        )

    def _add_json(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="output machine-readable JSON",
        )

    def _add_log_level(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--log-level",
            default="INFO",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            help="logging level (default: INFO)",
        )

    # ── login subcommand ─────────────────────────────────────────
    login_parser = subparsers.add_parser(
        "login",
        help="Login via QR code scan.",
    )
    login_parser.add_argument(
        "session_name",
        nargs="?",
        default=None,
        help="session name (default: default session)",
    )
    login_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        default=False,
        help="force new login even if credentials exist",
    )
    _add_base_path(login_parser)
    _add_json(login_parser)
    _add_log_level(login_parser)

    # ── logout subcommand ────────────────────────────────────────
    logout_parser = subparsers.add_parser(
        "logout",
        help="Log out a session.",
    )
    logout_parser.add_argument(
        "session_name",
        nargs="?",
        default=None,
        help="session name (default: default session)",
    )
    _add_base_path(logout_parser)
    _add_json(logout_parser)
    _add_log_level(logout_parser)

    # ── status subcommand ────────────────────────────────────────
    status_parser = subparsers.add_parser(
        "status",
        help="Show session connection status.",
    )
    _add_base_path(status_parser)
    _add_json(status_parser)
    _add_log_level(status_parser)

    # ── recv subcommand ──────────────────────────────────────────
    recv_parser = subparsers.add_parser(
        "recv",
        help="Receive messages.",
    )
    recv_parser.add_argument(
        "--timeout",
        "-t",
        type=float,
        default=5.0,
        help="max wait time in seconds (default: 5)",
    )
    _add_base_path(recv_parser)
    _add_json(recv_parser)
    _add_log_level(recv_parser)

    # ── send subcommand ──────────────────────────────────────────
    send_parser = subparsers.add_parser(
        "send",
        help="Send a message.",
    )
    send_parser.add_argument(
        "to",
        help="target user ID (e.g. xxx@im.wechat)",
    )
    send_parser.add_argument("--text", default=None, help="text content")
    send_parser.add_argument("--image", default=None, help="image file path")
    send_parser.add_argument("--file", default=None, help="file attachment path")
    send_parser.add_argument("--file-name", default=None, help="display name for file")
    send_parser.add_argument("--video", default=None, help="video file path")
    send_parser.add_argument("--voice", default=None, help="voice file path")
    _add_base_path(send_parser)
    _add_json(send_parser)
    _add_log_level(send_parser)

    # ── download subcommand ──────────────────────────────────────
    dl_parser = subparsers.add_parser(
        "download",
        help="Download media from a message.",
    )
    dl_parser.add_argument("message_id", help="message ID")
    dl_parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="output directory (default: ~/.weilink/downloads/)",
    )
    _add_base_path(dl_parser)
    _add_json(dl_parser)
    _add_log_level(dl_parser)

    # ── history subcommand ───────────────────────────────────────
    hist_parser = subparsers.add_parser(
        "history",
        help="Query message history.",
    )
    hist_parser.add_argument("--user", default=None, help="filter by user ID")
    hist_parser.add_argument("--bot", default=None, help="filter by bot ID")
    hist_parser.add_argument(
        "--type",
        default=None,
        help="filter by type: TEXT, IMAGE, VOICE, FILE, VIDEO",
    )
    hist_parser.add_argument(
        "--direction",
        default=None,
        help="filter: received or sent",
    )
    hist_parser.add_argument(
        "--since",
        default=None,
        help="start time (ISO 8601 or unix ms)",
    )
    hist_parser.add_argument(
        "--until",
        default=None,
        help="end time (ISO 8601 or unix ms)",
    )
    hist_parser.add_argument("--text", default=None, help="text substring search")
    hist_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="max results (default: 50)",
    )
    hist_parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="pagination offset",
    )
    _add_base_path(hist_parser)
    _add_json(hist_parser)
    _add_log_level(hist_parser)

    # ── sessions subcommand (with sub-subcommands) ───────────────
    sess_parser = subparsers.add_parser(
        "sessions",
        help="Session management (list, rename, set-default).",
    )
    _add_base_path(sess_parser)
    _add_json(sess_parser)
    _add_log_level(sess_parser)
    sess_sub = sess_parser.add_subparsers(dest="sessions_command")

    rename_parser = sess_sub.add_parser("rename", help="Rename a session.")
    rename_parser.add_argument("old_name", help="current session name")
    rename_parser.add_argument("new_name", help="new session name")
    _add_base_path(rename_parser)
    _add_json(rename_parser)

    default_parser = sess_sub.add_parser("default", help="Set the default session.")
    default_parser.add_argument("session_name", help="session name")
    _add_base_path(default_parser)
    _add_json(default_parser)

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

    # ── migrate subcommand ─────────────────────────────────────────
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="[Experimental] Migrate credentials from another tool.",
    )
    migrate_sub = migrate_parser.add_subparsers(dest="migrate_source", required=True)

    oc_parser = migrate_sub.add_parser(
        "openclaw",
        help="Migrate from OpenClaw weixin plugin (@tencent-weixin/openclaw-weixin).",
    )
    oc_parser.add_argument(
        "--source",
        default=None,
        help="OpenClaw state directory (default: ~/.openclaw)",
    )
    oc_parser.add_argument(
        "--base-path",
        "-d",
        default=None,
        help="weilink data directory (default: ~/.weilink/)",
    )
    oc_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="show what would be migrated without writing files",
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

    if args.command == "login":
        _run_login(args)
    elif args.command == "logout":
        _run_logout(args)
    elif args.command == "status":
        _run_status(args)
    elif args.command == "recv":
        _run_recv(args)
    elif args.command == "send":
        _run_send(args)
    elif args.command == "download":
        _run_download(args)
    elif args.command == "history":
        _run_history(args)
    elif args.command == "sessions":
        _run_sessions(args)
    elif args.command == "admin":
        _run_admin(args)
    elif args.command == "migrate":
        _run_migrate(args)
    elif args.command == "openapi":
        _run_openapi(args)
    elif args.command == "mcp":
        _run_mcp(args)


if __name__ == "__main__":
    main()
