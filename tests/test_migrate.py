"""Tests for weilink.migrate module."""

from __future__ import annotations

import json
from pathlib import Path


from weilink.migrate import migrate_openclaw


def _setup_openclaw(
    tmp_path: Path,
    accounts: list[dict[str, object]],
) -> Path:
    """Create a mock OpenClaw state directory.

    Each entry in *accounts* must have ``id`` (str) and optionally
    ``token``, ``baseUrl``, ``userId``, ``savedAt``, ``cursor``,
    ``context_tokens`` (dict[str, str]).
    """
    state_dir = tmp_path / "openclaw"
    weixin_dir = state_dir / "openclaw-weixin"
    accounts_dir = weixin_dir / "accounts"
    accounts_dir.mkdir(parents=True)

    ids = [a["id"] for a in accounts]
    (weixin_dir / "accounts.json").write_text(json.dumps(ids))

    for acct in accounts:
        aid = acct["id"]
        cred: dict[str, object] = {}
        if "token" in acct:
            cred["token"] = acct["token"]
        if "baseUrl" in acct:
            cred["baseUrl"] = acct["baseUrl"]
        if "userId" in acct:
            cred["userId"] = acct["userId"]
        if "savedAt" in acct:
            cred["savedAt"] = acct["savedAt"]
        if cred:
            (accounts_dir / f"{aid}.json").write_text(json.dumps(cred))

        if "cursor" in acct:
            sync = {"get_updates_buf": acct["cursor"]}
            (accounts_dir / f"{aid}.sync.json").write_text(json.dumps(sync))

        ctx = acct.get("context_tokens")
        if ctx:
            (accounts_dir / f"{aid}.context-tokens.json").write_text(json.dumps(ctx))

    return state_dir


class TestMigrateOpenclaw:
    def test_single_account(self, tmp_path: Path) -> None:
        source = _setup_openclaw(
            tmp_path,
            [
                {
                    "id": "abc123@im.bot",
                    "token": "tok_abc",
                    "baseUrl": "https://ilinkai.weixin.qq.com",
                    "userId": "user1@im.wechat",
                    "cursor": "cur_1",
                    "context_tokens": {"user1@im.wechat": "ctx_tok_1"},
                }
            ],
        )
        target = tmp_path / "weilink"

        results = migrate_openclaw(source, target)

        assert len(results) == 1
        r = results[0]
        assert r.status == "migrated"
        assert r.session_name == "abc123"
        assert r.account_id == "abc123@im.bot"

        token_data = json.loads((target / "abc123" / "token.json").read_text())
        assert token_data["bot_id"] == "abc123@im.bot"
        assert token_data["base_url"] == "https://ilinkai.weixin.qq.com"
        assert token_data["token"] == "tok_abc"
        assert token_data["user_id"] == "user1@im.wechat"
        assert token_data["cursor"] == "cur_1"

        ctx_data = json.loads((target / "abc123" / "contexts.json").read_text())
        assert "user1@im.wechat" in ctx_data
        assert ctx_data["user1@im.wechat"]["t"] == "ctx_tok_1"

    def test_multiple_accounts(self, tmp_path: Path) -> None:
        source = _setup_openclaw(
            tmp_path,
            [
                {"id": "a1@im.bot", "token": "tok_a1"},
                {"id": "a2@im.bot", "token": "tok_a2"},
            ],
        )
        target = tmp_path / "weilink"

        results = migrate_openclaw(source, target)

        assert len(results) == 2
        assert all(r.status == "migrated" for r in results)
        assert (target / "a1" / "token.json").exists()
        assert (target / "a2" / "token.json").exists()

    def test_dry_run(self, tmp_path: Path) -> None:
        source = _setup_openclaw(
            tmp_path,
            [{"id": "dry@im.bot", "token": "tok_dry"}],
        )
        target = tmp_path / "weilink"

        results = migrate_openclaw(source, target, dry_run=True)

        assert len(results) == 1
        assert results[0].status == "migrated"
        assert "[dry-run]" in results[0].detail
        assert not (target / "dry" / "token.json").exists()

    def test_skip_existing(self, tmp_path: Path) -> None:
        source = _setup_openclaw(
            tmp_path,
            [{"id": "exist@im.bot", "token": "tok_exist"}],
        )
        target = tmp_path / "weilink"

        # Pre-create session
        session_dir = target / "exist"
        session_dir.mkdir(parents=True)
        (session_dir / "token.json").write_text("{}")

        results = migrate_openclaw(source, target)

        assert len(results) == 1
        assert results[0].status == "skipped"

    def test_missing_accounts_json(self, tmp_path: Path) -> None:
        source = tmp_path / "empty"
        source.mkdir()
        target = tmp_path / "weilink"

        results = migrate_openclaw(source, target)

        assert len(results) == 1
        assert results[0].status == "error"
        assert "accounts.json not found" in results[0].detail

    def test_missing_credential_file(self, tmp_path: Path) -> None:
        """Account listed in index but no .json file."""
        state_dir = tmp_path / "openclaw"
        weixin_dir = state_dir / "openclaw-weixin"
        accounts_dir = weixin_dir / "accounts"
        accounts_dir.mkdir(parents=True)
        (weixin_dir / "accounts.json").write_text('["ghost@im.bot"]')

        target = tmp_path / "weilink"

        results = migrate_openclaw(state_dir, target)

        assert len(results) == 1
        assert results[0].status == "error"
        assert "not found" in results[0].detail

    def test_empty_token(self, tmp_path: Path) -> None:
        source = _setup_openclaw(
            tmp_path,
            [{"id": "notoken@im.bot", "token": ""}],
        )
        target = tmp_path / "weilink"

        results = migrate_openclaw(source, target)

        assert len(results) == 1
        assert results[0].status == "error"
        assert "No token" in results[0].detail

    def test_default_base_url(self, tmp_path: Path) -> None:
        """baseUrl should default when not specified."""
        source = _setup_openclaw(
            tmp_path,
            [{"id": "nourl@im.bot", "token": "tok_nourl"}],
        )
        target = tmp_path / "weilink"

        results = migrate_openclaw(source, target)

        assert results[0].status == "migrated"
        data = json.loads((target / "nourl" / "token.json").read_text())
        assert data["base_url"] == "https://ilinkai.weixin.qq.com"

    def test_normalized_account_id(self, tmp_path: Path) -> None:
        """Handle OpenClaw normalized IDs (dashes instead of @/dots)."""
        source = _setup_openclaw(
            tmp_path,
            [{"id": "abc123-im-bot", "token": "tok_norm"}],
        )
        target = tmp_path / "weilink"

        results = migrate_openclaw(source, target)

        assert results[0].status == "migrated"
        assert results[0].session_name == "abc123"

    def test_no_context_tokens_file(self, tmp_path: Path) -> None:
        """contexts.json should not be created when no context tokens exist."""
        source = _setup_openclaw(
            tmp_path,
            [{"id": "noctx@im.bot", "token": "tok_noctx"}],
        )
        target = tmp_path / "weilink"

        results = migrate_openclaw(source, target)

        assert results[0].status == "migrated"
        assert (target / "noctx" / "token.json").exists()
        assert not (target / "noctx" / "contexts.json").exists()

    def test_saved_at_parsed(self, tmp_path: Path) -> None:
        source = _setup_openclaw(
            tmp_path,
            [
                {
                    "id": "ts@im.bot",
                    "token": "tok_ts",
                    "savedAt": "2026-03-25T10:00:00.000Z",
                }
            ],
        )
        target = tmp_path / "weilink"

        results = migrate_openclaw(source, target)

        assert results[0].status == "migrated"
        data = json.loads((target / "ts" / "token.json").read_text())
        # Should be around 2026-03-25T10:00:00Z epoch
        assert 1774000000 < data["created_at"] < 1774700000
