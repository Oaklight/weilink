"""Universal hook-poll engine for AI coding CLI integrations.

Reads the WeiLink SQLite message store for new messages since the last
check, formats them as human-readable text, and outputs JSON.  State is
tracked in ``~/.weilink/.hook_state.json``.

This module is used by ``weilink hook-poll`` and indirectly by the thin
hook wrapper scripts shipped for Claude Code / Codex.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_LIMIT = 20
_DEFAULT_LOOKBACK_S = 300  # 5 minutes


def _state_path(base_path: Path) -> Path:
    return base_path / ".hook_state.json"


def _load_last_ts(state_file: Path) -> int:
    """Load last-check timestamp (unix ms) from state file."""
    try:
        data = json.loads(state_file.read_text())
        return int(data.get("last_ts", 0))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return 0


def _save_last_ts(state_file: Path, ts_ms: int) -> None:
    """Persist last-check timestamp."""
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({"last_ts": ts_ms}))
    except OSError:
        pass


def _format_message(msg: dict[str, Any]) -> str:
    """Format a single message dict into a readable line."""
    from_user = msg.get("from_user", "unknown")
    text = msg.get("text", "")
    msg_type = msg.get("msg_type", "TEXT")
    ts = msg.get("timestamp", 0)

    try:
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%H:%M:%S")
    except (ValueError, OSError):
        dt = "??:??:??"

    line = f"[{dt}] {from_user} ({msg_type})"

    if text:
        line += f": {text}"

    if msg_type == "IMAGE" and msg.get("image"):
        line += " [image]"
    elif msg_type == "VOICE" and msg.get("voice"):
        voice = msg["voice"]
        line += f" [voice {voice.get('playtime', 0)}ms]"
        if voice.get("text"):
            line += f" transcription: {voice['text']}"
    elif msg_type == "FILE" and msg.get("file"):
        line += f" [file: {msg['file'].get('file_name', '?')}]"
    elif msg_type == "VIDEO":
        line += " [video]"

    ref = msg.get("ref_msg")
    if ref and ref.get("text"):
        line += f" (reply to: {ref['text'][:40]})"

    return line


def hook_poll(
    base_path: Path | None = None,
    limit: int = _DEFAULT_LIMIT,
    reset: bool = False,
) -> dict[str, Any]:
    """Core poll logic.  Returns a dict with poll results.

    Args:
        base_path: WeiLink data directory (default ``~/.weilink/``).
        limit: Maximum number of messages to return.
        reset: If True, clear the state file and return empty result.

    Returns:
        ``{"has_messages": bool, "count": int, "context": str}``
    """
    from weilink import WeiLink

    if base_path is None:
        base_path = Path.home() / ".weilink"

    state_file = _state_path(base_path)

    if reset:
        try:
            state_file.unlink(missing_ok=True)
        except OSError:
            pass
        return {"has_messages": False, "count": 0, "context": ""}

    from weilink._vendor.filelock import FileLock

    # Serialize concurrent hook-poll invocations (e.g. multiple IDE
    # instances) so each one sees a consistent last_ts.
    hook_lock = FileLock(base_path / ".hook.lock")
    with hook_lock:
        last_ts = _load_last_ts(state_file)
        if last_ts == 0:
            last_ts = int((time.time() - _DEFAULT_LOOKBACK_S) * 1000)

        now_ms = int(time.time() * 1000)

        # Read directly from SQLite store — fast, no network.
        wl = WeiLink(base_path=base_path, message_store=True)
        store = wl._message_store
        if store is None:
            wl.close()
            _save_last_ts(state_file, now_ms)
            return {"has_messages": False, "count": 0, "context": ""}

        try:
            messages = store.query(direction=1, since_ms=last_ts, limit=limit)
        except Exception:
            messages = []
        finally:
            wl.close()

        _save_last_ts(state_file, now_ms)

    if not messages:
        return {"has_messages": False, "count": 0, "context": ""}

    lines = ["== New WeChat Messages =="]
    for msg in messages:
        lines.append(_format_message(msg))
    lines.append(
        f"\n{len(messages)} new message(s). Use WeiLink MCP tools to respond if needed."
    )

    return {
        "has_messages": True,
        "count": len(messages),
        "context": "\n".join(lines),
    }


def run_hook_poll(argv: list[str] | None = None) -> None:
    """CLI entry point for ``weilink hook-poll``."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="weilink hook-poll",
        description="Poll WeiLink message store for new messages (internal).",
    )
    parser.add_argument(
        "--base-path",
        "-d",
        default=None,
        help="data directory (default: ~/.weilink/)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_LIMIT,
        help=f"max messages to return (default: {_DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="clear state file and exit",
    )

    args = parser.parse_args(argv)
    bp = Path(args.base_path) if args.base_path else None

    try:
        result = hook_poll(base_path=bp, limit=args.limit, reset=args.reset)
    except Exception as exc:
        result = {"has_messages": False, "count": 0, "context": "", "error": str(exc)}

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
