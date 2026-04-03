#!/usr/bin/env python3
"""WeiLink UserPromptSubmit hook for Claude Code / Codex.

Polls the WeiLink message store for new WeChat messages and injects
them into the conversation context via ``additionalContext``.

This script is invoked by the CLI hook system.  It delegates the actual
polling to ``weilink hook-poll`` so the logic stays in one place.
If the ``weilink`` CLI is not on PATH (e.g. installed in a conda env),
it falls back to a direct in-process import.
"""

import json
import subprocess
import sys


def _poll_via_cli() -> dict | None:
    """Try the CLI subprocess.  Returns parsed dict or None on failure."""
    try:
        result = subprocess.run(
            ["weilink", "hook-poll"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


def _poll_via_import() -> dict | None:
    """Fallback: import the hook engine directly (no subprocess)."""
    try:
        from weilink._cli import hook_poll

        return hook_poll()
    except Exception:
        pass
    return None


def main() -> None:
    # Read hook input from stdin (required by protocol, content ignored).
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    data = _poll_via_cli() or _poll_via_import() or {}

    # Wrap as hook output.
    if data.get("has_messages") and data.get("context"):
        print(json.dumps({"additionalContext": data["context"]}))
    else:
        print(json.dumps({}))

    sys.exit(0)


if __name__ == "__main__":
    main()
