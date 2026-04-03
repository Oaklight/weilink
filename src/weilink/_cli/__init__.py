"""CLI support utilities (banner, hook-poll, setup helpers).

Not part of the public API.
"""

from weilink._cli._banner import display_startup_banner, version_check
from weilink._cli._hook import hook_poll, run_hook_poll
from weilink._cli._setup import (
    SetupResult,
    setup_claude_code,
    setup_codex,
    setup_opencode,
)

__all__ = [
    "SetupResult",
    "display_startup_banner",
    "hook_poll",
    "run_hook_poll",
    "setup_claude_code",
    "setup_codex",
    "setup_opencode",
    "version_check",
]
