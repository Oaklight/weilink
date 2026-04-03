"""Setup helpers for AI coding CLI integrations.

Provides ``setup_claude_code`` and ``setup_codex`` which install the
WeiLink plugin / hook / skill assets into the target CLI's configuration
directory.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_INTEGRATIONS = Path(__file__).resolve().parent.parent / "integrations"


@dataclass
class SetupResult:
    """Result of a setup / teardown operation."""

    target: str
    action: Literal[
        "installed",
        "uninstalled",
        "already_installed",
        "not_installed",
        "error",
    ]
    detail: str


# ── Claude Code ─────────────────────────────────────────────────────


def _claude_plugin_dir() -> Path:
    return Path.home() / ".claude" / "plugins" / "weilink"


def _claude_source_dir() -> Path:
    return _INTEGRATIONS / "claude_code"


def setup_claude_code(
    *,
    uninstall: bool = False,
    copy: bool = False,
) -> SetupResult:
    """Install or remove the WeiLink Claude Code plugin.

    By default a symlink is created so pip upgrades take effect
    automatically.  Pass *copy=True* to copy files instead (useful on
    Windows or when symlinks are not supported).
    """
    target = _claude_plugin_dir()
    source = _claude_source_dir()

    if uninstall:
        if not target.exists() and not target.is_symlink():
            return SetupResult(
                "claude-code",
                "not_installed",
                f"Plugin not found at {target}",
            )
        if target.is_symlink():
            target.unlink()
        else:
            shutil.rmtree(target)
        return SetupResult(
            "claude-code", "uninstalled", f"Removed plugin from {target}"
        )

    # Install
    if target.exists() or target.is_symlink():
        if target.is_symlink() and target.resolve() == source.resolve():
            return SetupResult(
                "claude-code",
                "already_installed",
                f"Plugin already installed at {target}",
            )
        # Remove stale version before re-installing.
        if target.is_symlink():
            target.unlink()
        else:
            shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)

    if copy:
        shutil.copytree(source, target)
        return SetupResult(
            "claude-code",
            "installed",
            f"Plugin copied to {target}",
        )

    target.symlink_to(source)
    return SetupResult(
        "claude-code",
        "installed",
        f"Plugin symlinked: {target} -> {source}",
    )


# ── OpenCode ──────────────────────────────────────────────────────


def _opencode_config_path() -> Path:
    return Path.home() / ".config" / "opencode" / "opencode.json"


def _opencode_commands_dir() -> Path:
    return Path.home() / ".config" / "opencode" / "commands"


def _opencode_source_dir() -> Path:
    return _INTEGRATIONS / "opencode"


def _merge_opencode_mcp(config_path: Path) -> None:
    """Add ``mcp.weilink`` entry to opencode.json."""
    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    mcp = existing.setdefault("mcp", {})
    mcp["weilink"] = {
        "type": "local",
        "command": ["weilink", "mcp"],
        "enabled": True,
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(existing, indent=2) + "\n")


def _remove_opencode_mcp(config_path: Path) -> bool:
    """Remove ``mcp.weilink`` entry from opencode.json.  Returns True if changed."""
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    mcp = data.get("mcp", {})
    if "weilink" not in mcp:
        return False

    del mcp["weilink"]
    if not mcp:
        data.pop("mcp", None)
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    return True


def setup_opencode(
    *,
    uninstall: bool = False,
) -> SetupResult:
    """Install or remove WeiLink integration for OpenCode.

    Installs:
      1. MCP server entry merged into ``~/.config/opencode/opencode.json``
      2. Slash command to ``~/.config/opencode/commands/weilink.md``

    Note: OpenCode does not support shell-based hooks, so auto-polling
    of new messages is not available.  Users can call the ``recv`` MCP
    tool or use the ``/weilink check`` command instead.
    """
    config_path = _opencode_config_path()
    command_file = _opencode_commands_dir() / "weilink.md"
    source = _opencode_source_dir()

    if uninstall:
        removed: list[str] = []
        if command_file.exists():
            command_file.unlink()
            removed.append(str(command_file))
        if _remove_opencode_mcp(config_path):
            removed.append(str(config_path) + " (mcp.weilink removed)")
        if not removed:
            return SetupResult("opencode", "not_installed", "No WeiLink files found")
        return SetupResult(
            "opencode",
            "uninstalled",
            f"Removed: {', '.join(removed)}",
        )

    # Install MCP config
    _merge_opencode_mcp(config_path)

    # Install command
    _opencode_commands_dir().mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "commands" / "weilink.md", command_file)

    return SetupResult(
        "opencode",
        "installed",
        f"Installed MCP config and command.\n"
        f"  Config: {config_path}\n"
        f"  Command: {command_file}",
    )


# ── Codex ───────────────────────────────────────────────────────────


def _codex_source_dir() -> Path:
    return _INTEGRATIONS / "codex"


def _codex_hooks_dir() -> Path:
    return Path.home() / ".codex" / "hooks"


def _codex_hooks_json() -> Path:
    return Path.home() / ".codex" / "hooks.json"


def _codex_commands_dir() -> Path:
    return Path.home() / ".codex" / "commands"


def _merge_hooks_json(target_path: Path, source_path: Path) -> None:
    """Merge WeiLink hook entries into the target hooks.json."""
    source_data = json.loads(source_path.read_text())
    source_hooks = source_data.get("hooks", {})

    existing: dict = {}
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    if "hooks" not in existing:
        existing["hooks"] = {}

    for event, entries in source_hooks.items():
        if event not in existing["hooks"]:
            existing["hooks"][event] = entries
        else:
            # Avoid duplicates: check if a weilink hook is already there.
            has_weilink = any(
                "weilink" in str(h)
                for group in existing["hooks"][event]
                for h in group.get("hooks", [])
            )
            if not has_weilink:
                existing["hooks"][event].extend(entries)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(existing, indent=2) + "\n")


def _remove_weilink_hooks(target_path: Path) -> None:
    """Remove WeiLink hook entries from the target hooks.json."""
    if not target_path.exists():
        return
    try:
        data = json.loads(target_path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    hooks = data.get("hooks", {})
    for event in list(hooks.keys()):
        hooks[event] = [
            group
            for group in hooks[event]
            if not any("weilink" in str(h) for h in group.get("hooks", []))
        ]
        if not hooks[event]:
            del hooks[event]

    target_path.write_text(json.dumps(data, indent=2) + "\n")


def setup_codex(
    *,
    uninstall: bool = False,
    copy: bool = False,  # unused, kept for API consistency
) -> SetupResult:
    """Install or remove WeiLink integration for OpenAI Codex CLI.

    Installs:
      1. Hook script to ``~/.codex/hooks/weilink_poll_inject.py``
      2. Hook registration merged into ``~/.codex/hooks.json``
      3. Slash command to ``~/.codex/commands/weilink.md``

    MCP registration must be done separately:
      ``codex mcp add weilink -- weilink mcp``
    """
    source = _codex_source_dir()
    hook_script = _codex_hooks_dir() / "weilink_poll_inject.py"
    command_file = _codex_commands_dir() / "weilink.md"

    if uninstall:
        removed: list[str] = []
        if hook_script.exists():
            hook_script.unlink()
            removed.append(str(hook_script))
        if command_file.exists():
            command_file.unlink()
            removed.append(str(command_file))
        _remove_weilink_hooks(_codex_hooks_json())
        if removed:
            removed.append(str(_codex_hooks_json()) + " (hooks cleaned)")
        if not removed:
            return SetupResult("codex", "not_installed", "No WeiLink files found")
        return SetupResult(
            "codex",
            "uninstalled",
            f"Removed: {', '.join(removed)}",
        )

    # Install hook script
    _codex_hooks_dir().mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "hooks" / "poll_inject.py", hook_script)

    # Merge hook registration
    _merge_hooks_json(_codex_hooks_json(), source / "hooks.json")

    # Install command
    _codex_commands_dir().mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "commands" / "weilink.md", command_file)

    return SetupResult(
        "codex",
        "installed",
        f"Installed hook, command, and hooks.json entry.\n"
        f"  Hook script: {hook_script}\n"
        f"  Command: {command_file}\n"
        f"  Hooks config: {_codex_hooks_json()}\n"
        f"\n"
        f"  Register MCP server manually:\n"
        f"    codex mcp add weilink -- weilink mcp",
    )
