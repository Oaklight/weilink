"""Tests for weilink.server.app — MCP / OpenAPI tool functions."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from unittest.mock import MagicMock, patch

import pytest

from weilink.models import Message, MessageType, SendResult
from weilink.server import app


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _run(coro):
    """Run an async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_mock_client(connected: bool = True) -> MagicMock:
    """Create a mock WeiLink client with sensible defaults."""
    wl = MagicMock()
    wl.is_connected = connected
    wl.sessions = {"default": MagicMock()}
    wl.bot_ids = {"default": "bot1@im.bot"} if connected else {}
    wl._message_store = None
    return wl


def _reset_module_state() -> None:
    """Reset module-level state between tests."""
    app._wl = None
    app._message_cache.clear()
    app._pending_login = None


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset server module state before each test."""
    _reset_module_state()
    yield
    _reset_module_state()


# ------------------------------------------------------------------
# recv
# ------------------------------------------------------------------


class TestRecv:
    def test_returns_messages(self):
        wl = _make_mock_client()
        msg = Message(
            from_user="user1@im.wechat",
            msg_type=MessageType.TEXT,
            text="hello",
            timestamp=1000,
            message_id=1,
            bot_id="bot1@im.bot",
        )
        wl.recv.return_value = [msg]
        app._wl = wl

        result = json.loads(_run(app.recv(timeout=1.0)))
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["text"] == "hello"

    def test_not_connected(self):
        wl = _make_mock_client(connected=False)
        app._wl = wl

        result = json.loads(_run(app.recv()))
        assert "error" in result
        assert "Not logged in" in result["error"]

    def test_caches_messages(self):
        wl = _make_mock_client()
        msg = Message(
            from_user="user1@im.wechat",
            msg_type=MessageType.TEXT,
            text="cached",
            timestamp=1000,
            message_id=42,
            bot_id="bot1@im.bot",
        )
        wl.recv.return_value = [msg]
        app._wl = wl

        _run(app.recv())
        assert "42" in app._message_cache


# ------------------------------------------------------------------
# send
# ------------------------------------------------------------------


class TestSend:
    def test_sends_text(self):
        wl = _make_mock_client()
        wl.send.return_value = SendResult(success=True, messages=[], remaining=0)
        app._wl = wl

        result = json.loads(_run(app.send(to="user1@im.wechat", text="hi")))
        assert result["success"] is True
        wl.send.assert_called_once()

    def test_not_connected(self):
        wl = _make_mock_client(connected=False)
        app._wl = wl

        result = json.loads(_run(app.send(to="user1@im.wechat", text="hi")))
        assert "error" in result

    def test_no_content(self):
        wl = _make_mock_client()
        app._wl = wl

        result = json.loads(_run(app.send(to="user1@im.wechat")))
        assert "error" in result
        assert "No content" in result["error"]


# ------------------------------------------------------------------
# download
# ------------------------------------------------------------------


class TestDownload:
    def test_from_cache(self, tmp_path):
        wl = _make_mock_client()
        msg = Message(
            from_user="user1@im.wechat",
            msg_type=MessageType.IMAGE,
            timestamp=1000,
            message_id=10,
            bot_id="bot1@im.bot",
        )
        app._message_cache["10"] = msg
        wl.download.return_value = b"\xff\xd8\xff\xe0"  # JPEG magic bytes
        app._wl = wl

        result = json.loads(_run(app.download("10", save_dir=str(tmp_path))))
        assert "path" in result
        assert result["size"] == 4

    def test_not_found(self):
        wl = _make_mock_client()
        wl._message_store = None
        app._wl = wl

        result = json.loads(_run(app.download("999")))
        assert "error" in result
        assert "not found" in result["error"]


# ------------------------------------------------------------------
# history
# ------------------------------------------------------------------


class TestHistory:
    def test_store_disabled(self):
        wl = _make_mock_client()
        wl._message_store = None
        app._wl = wl

        result = json.loads(app.history())
        assert "error" in result
        assert "not enabled" in result["error"]

    def test_queries_store(self):
        wl = _make_mock_client()
        store = MagicMock()
        store.count.return_value = 1
        store.query.return_value = [
            {"text": "hello", "msg_type": "TEXT", "direction": "received"}
        ]
        wl._message_store = store
        app._wl = wl

        result = json.loads(app.history(limit=10))
        assert result["total"] == 1
        assert len(result["messages"]) == 1


# ------------------------------------------------------------------
# sessions
# ------------------------------------------------------------------


class TestSessions:
    def test_lists_sessions(self):
        wl = _make_mock_client()
        wl.sessions = {"default": MagicMock(), "work": MagicMock()}
        wl.bot_ids = {"default": "bot1@im.bot"}
        app._wl = wl

        result = json.loads(app.sessions())
        assert isinstance(result, list)
        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"default", "work"}
        # default is connected, work is not
        by_name = {s["name"]: s for s in result}
        assert by_name["default"]["connected"] is True
        assert by_name["work"]["connected"] is False


# ------------------------------------------------------------------
# login (merged flow)
# ------------------------------------------------------------------


class TestLogin:
    def test_first_call_returns_qr(self):
        with patch("weilink._protocol.get_qr_code") as mock_qr:
            mock_qr.return_value = {
                "qrcode": "qr123",
                "qrcode_img_content": "https://example.com/qr.png",
            }
            result = json.loads(_run(app.login()))

        assert result["status"] == "pending"
        assert "qr_url" in result
        assert app._pending_login is not None

    def test_second_call_polls(self):
        # Set up pending login
        app._pending_login = {
            "qrcode": "qr123",
            "session_name": None,
            "created_at": __import__("time").time(),
        }

        with patch("weilink._protocol.poll_qr_status") as mock_poll:
            mock_poll.return_value = {"status": "scaned"}
            result = json.loads(_run(app.login()))

        assert result["status"] == "scanned"

    def test_confirmed_initializes_session(self):
        app._pending_login = {
            "qrcode": "qr123",
            "session_name": None,
            "created_at": __import__("time").time(),
        }

        wl = _make_mock_client(connected=False)
        wl._default_session = MagicMock()
        wl._base_path = MagicMock()
        app._wl = wl

        with patch("weilink._protocol.poll_qr_status") as mock_poll:
            mock_poll.return_value = {
                "status": "confirmed",
                "bot_token": "tok123",
                "baseurl": "https://api.example.com",
                "ilink_bot_id": "bot1@im.bot",
                "ilink_user_id": "user1",
            }
            result = json.loads(_run(app.login()))

        assert result["status"] == "confirmed"
        assert result["bot_id"] == "bot1@im.bot"
        assert app._pending_login is None

    def test_force_restarts_flow(self):
        app._pending_login = {
            "qrcode": "old_qr",
            "session_name": None,
            "created_at": __import__("time").time(),
        }

        with patch("weilink._protocol.get_qr_code") as mock_qr:
            mock_qr.return_value = {
                "qrcode": "new_qr",
                "qrcode_img_content": "https://example.com/new_qr.png",
            }
            result = json.loads(_run(app.login(force=True)))

        assert result["status"] == "pending"
        assert app._pending_login["qrcode"] == "new_qr"

    def test_expired_clears_state(self):
        app._pending_login = {
            "qrcode": "qr123",
            "session_name": None,
            "created_at": __import__("time").time(),
        }

        with patch("weilink._protocol.poll_qr_status") as mock_poll:
            mock_poll.return_value = {"status": "expired"}
            result = json.loads(_run(app.login()))

        assert result["status"] == "expired"
        assert app._pending_login is None


# ------------------------------------------------------------------
# logout
# ------------------------------------------------------------------


class TestLogout:
    def test_success(self):
        wl = _make_mock_client()
        app._wl = wl

        result = json.loads(_run(app.logout()))
        assert result["success"] is True
        assert result["session"] == "default"

    def test_with_session_name(self):
        wl = _make_mock_client()
        app._wl = wl

        result = json.loads(_run(app.logout(session_name="work")))
        assert result["success"] is True
        assert result["session"] == "work"

    def test_error(self):
        wl = _make_mock_client()
        wl.logout.side_effect = KeyError("Session 'unknown' not found")
        app._wl = wl

        result = json.loads(_run(app.logout(session_name="unknown")))
        assert "error" in result


# ------------------------------------------------------------------
# rename_session
# ------------------------------------------------------------------


class TestRenameSession:
    def test_success(self):
        wl = _make_mock_client()
        app._wl = wl

        result = json.loads(app.rename_session("default", "main"))
        assert result["success"] is True
        assert result["old_name"] == "default"
        assert result["new_name"] == "main"
        wl.rename_session.assert_called_once_with("default", "main")

    def test_error(self):
        wl = _make_mock_client()
        wl.rename_session.side_effect = ValueError("Name conflict")
        app._wl = wl

        result = json.loads(app.rename_session("default", "work"))
        assert "error" in result


# ------------------------------------------------------------------
# set_default
# ------------------------------------------------------------------


class TestSetDefault:
    def test_success(self):
        wl = _make_mock_client()
        app._wl = wl

        result = json.loads(app.set_default("work"))
        assert result["success"] is True
        assert result["default_session"] == "work"
        wl.set_default.assert_called_once_with("work")

    def test_error(self):
        wl = _make_mock_client()
        wl.set_default.side_effect = KeyError("Session 'unknown' not found")
        app._wl = wl

        result = json.loads(app.set_default("unknown"))
        assert "error" in result


# ------------------------------------------------------------------
# build_registry
# ------------------------------------------------------------------


@pytest.mark.skipif(
    not importlib.util.find_spec("toolregistry"),
    reason="toolregistry not installed",
)
class TestRegistry:
    def test_builds_with_all_tools(self):
        registry = app.build_registry()
        tool_names = [t["function"]["name"] for t in registry.get_tools_json()]
        expected = [
            "recv",
            "send",
            "download",
            "history",
            "sessions",
            "login",
            "logout",
            "rename_session",
            "set_default",
        ]
        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"
        # check_login should NOT be present
        assert "check_login" not in tool_names
