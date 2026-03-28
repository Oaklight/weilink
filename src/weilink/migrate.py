"""Migrate credentials from other iLink Bot tools to WeiLink.

.. note:: **Experimental** — This module's API may change in future releases.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_OPENCLAW_STATE_DIR = "~/.openclaw"
DEFAULT_ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"


@dataclass
class MigrateResult:
    """Result of migrating a single account."""

    account_id: str
    session_name: str
    status: Literal["migrated", "skipped", "error"]
    detail: str


def _derive_session_name(account_id: str) -> str:
    """Derive a weilink session name from an OpenClaw account ID.

    Examples:
        ``b0f5860fdecb@im.bot`` → ``b0f5860fdecb``
        ``b0f5860fdecb-im-bot`` → ``b0f5860fdecb``
    """
    name = account_id
    for suffix in ("@im.bot", "-im-bot"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def migrate_openclaw(
    source_dir: Path,
    target_dir: Path,
    *,
    dry_run: bool = False,
) -> list[MigrateResult]:
    """Migrate credentials from OpenClaw weixin plugin to WeiLink.

    Args:
        source_dir: OpenClaw state directory (default ``~/.openclaw``).
        target_dir: WeiLink data directory (default ``~/.weilink/``).
        dry_run: If True, report what would happen without writing files.

    Returns:
        List of per-account migration results.
    """
    weixin_dir = source_dir / "openclaw-weixin"
    accounts_index = weixin_dir / "accounts.json"
    accounts_dir = weixin_dir / "accounts"

    if not accounts_index.exists():
        return [
            MigrateResult(
                account_id="",
                session_name="",
                status="error",
                detail=f"accounts.json not found at {accounts_index}",
            )
        ]

    try:
        account_ids: list[str] = json.loads(accounts_index.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return [
            MigrateResult(
                account_id="",
                session_name="",
                status="error",
                detail=f"Failed to read accounts.json: {e}",
            )
        ]

    if not account_ids:
        return [
            MigrateResult(
                account_id="",
                session_name="",
                status="error",
                detail="No accounts found in accounts.json",
            )
        ]

    results: list[MigrateResult] = []
    now = time.time()

    for account_id in account_ids:
        session_name = _derive_session_name(account_id)
        session_dir = target_dir / session_name
        token_path = session_dir / "token.json"

        # Skip if session already exists
        if token_path.exists():
            results.append(
                MigrateResult(
                    account_id=account_id,
                    session_name=session_name,
                    status="skipped",
                    detail=f"Session already exists at {session_dir}",
                )
            )
            continue

        # Read account credentials
        cred_file = accounts_dir / f"{account_id}.json"
        if not cred_file.exists():
            results.append(
                MigrateResult(
                    account_id=account_id,
                    session_name=session_name,
                    status="error",
                    detail=f"Credential file not found: {cred_file}",
                )
            )
            continue

        try:
            cred = json.loads(cred_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            results.append(
                MigrateResult(
                    account_id=account_id,
                    session_name=session_name,
                    status="error",
                    detail=f"Failed to read credentials: {e}",
                )
            )
            continue

        token = cred.get("token", "")
        if not token:
            results.append(
                MigrateResult(
                    account_id=account_id,
                    session_name=session_name,
                    status="error",
                    detail="No token in credential file",
                )
            )
            continue

        base_url = cred.get("baseUrl", "") or DEFAULT_ILINK_BASE_URL
        user_id = cred.get("userId", "")

        # Parse savedAt as created_at
        saved_at = cred.get("savedAt", "")
        created_at = now
        if saved_at:
            try:
                from datetime import datetime, timezone

                # Python 3.10 fromisoformat doesn't accept trailing "Z"
                created_at = (
                    datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
                    .replace(tzinfo=timezone.utc)
                    .timestamp()
                )
            except (ValueError, TypeError):
                pass

        # Read sync buf (cursor)
        cursor = ""
        sync_file = accounts_dir / f"{account_id}.sync.json"
        if sync_file.exists():
            try:
                sync_data = json.loads(sync_file.read_text())
                cursor = sync_data.get("get_updates_buf", "")
            except (json.JSONDecodeError, OSError):
                pass

        # Read context tokens
        contexts: dict[str, dict[str, object]] = {}
        ctx_file = accounts_dir / f"{account_id}.context-tokens.json"
        if ctx_file.exists():
            try:
                raw_ctx: dict[str, str] = json.loads(ctx_file.read_text())
                for uid, ctx_token in raw_ctx.items():
                    if isinstance(ctx_token, str) and ctx_token:
                        contexts[uid] = {"t": ctx_token, "ts": now}
            except (json.JSONDecodeError, OSError):
                pass

        # Build weilink token.json
        token_data = {
            "bot_id": account_id,
            "base_url": base_url,
            "token": token,
            "user_id": user_id,
            "cursor": cursor,
            "created_at": created_at,
        }

        if dry_run:
            results.append(
                MigrateResult(
                    account_id=account_id,
                    session_name=session_name,
                    status="migrated",
                    detail=f"[dry-run] Would write to {session_dir}",
                )
            )
            continue

        # Write files
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            token_path.write_text(json.dumps(token_data, indent=2))
            if contexts:
                contexts_path = session_dir / "contexts.json"
                contexts_path.write_text(json.dumps(contexts, indent=2))
        except OSError as e:
            results.append(
                MigrateResult(
                    account_id=account_id,
                    session_name=session_name,
                    status="error",
                    detail=f"Failed to write: {e}",
                )
            )
            continue

        results.append(
            MigrateResult(
                account_id=account_id,
                session_name=session_name,
                status="migrated",
                detail=f"Migrated to {session_dir}",
            )
        )

    return results
