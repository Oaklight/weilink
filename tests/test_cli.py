"""Tests for the unified weilink CLI."""

import json
import subprocess
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from weilink.cli import main as cli_main
from weilink.models import BotInfo, Message, MessageType, SendResult


def _kill_proc(proc: subprocess.Popen) -> None:
    """Terminate a subprocess, falling back to SIGKILL if it won't die."""
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _make_mock_session(
    name: str = "default",
    bot_id: str | None = "bot1@im.bot",
    user_id: str | None = "user1@im.wechat",
    connected: bool = True,
    is_default: bool = True,
) -> MagicMock:
    """Create a mock Session object."""
    s = MagicMock()
    s.name = name
    s.bot_id = bot_id
    s.user_id = user_id
    s.is_connected = connected
    s.is_default = is_default
    return s


def _make_mock_client(
    connected: bool = True,
    sessions: dict | None = None,
) -> MagicMock:
    """Create a mock WeiLink client for CLI tests."""
    wl = MagicMock()
    wl.is_connected = connected
    wl._message_store = None

    if sessions is None:
        s = _make_mock_session(connected=connected)
        sessions = {"default": s}

    type(wl).sessions = PropertyMock(return_value=sessions)
    return wl


# ------------------------------------------------------------------
# Arg parsing (subprocess)
# ------------------------------------------------------------------


class TestCLIArgParsing:
    """Tests for CLI argument parsing without starting servers."""

    def test_no_subcommand_shows_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_admin_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli", "admin", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--host" in result.stdout
        assert "--port" in result.stdout
        assert "--base-path" in result.stdout
        assert "--no-banner" in result.stdout

    def test_mcp_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli", "mcp", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--transport" in result.stdout
        assert "stdio" in result.stdout
        assert "sse" in result.stdout
        assert "streamable-http" in result.stdout
        assert "http" in result.stdout
        assert "--admin-port" in result.stdout
        assert "--no-banner" in result.stdout

    def test_help_shows_grouped_commands(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "bot commands:" in result.stdout
        assert "server commands:" in result.stdout
        assert "other commands:" in result.stdout

    def test_login_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli", "login", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--json" in result.stdout
        assert "--force" in result.stdout
        assert "--base-path" in result.stdout

    def test_send_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli", "send", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--text" in result.stdout
        assert "--image" in result.stdout
        assert "--file" in result.stdout
        assert "--video" in result.stdout
        assert "--voice" in result.stdout

    def test_sessions_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli", "sessions", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "rename" in result.stdout
        assert "default" in result.stdout


# ------------------------------------------------------------------
# Admin / legacy (subprocess, integration)
# ------------------------------------------------------------------


class TestCLIAdmin:
    """Tests for the admin subcommand via the unified CLI."""

    def test_admin_starts_and_responds(self, tmp_path):
        proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "weilink.cli",
                "admin",
                "--no-banner",
                "--port",
                "0",
                "-d",
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert proc.stdout is not None
            url = None
            for _ in range(50):
                line = proc.stdout.readline()
                if "Admin panel:" in line:
                    url = line.strip().split()[-1]
                    break
            assert url is not None, "CLI did not print the URL"

            import urllib.request

            req = urllib.request.Request(url + "/api/status")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            assert "version" in data
        finally:
            _kill_proc(proc)

    def test_admin_via_legacy_entry_point(self, tmp_path):
        """weilink-admin (via python -m weilink.admin) delegates to unified CLI."""
        proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "weilink.admin",
                "--no-banner",
                "--port",
                "0",
                "-d",
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert proc.stdout is not None
            url = None
            for _ in range(50):
                line = proc.stdout.readline()
                if "Admin panel:" in line:
                    url = line.strip().split()[-1]
                    break
            assert url is not None, "Legacy CLI did not print the URL"
        finally:
            _kill_proc(proc)


# ------------------------------------------------------------------
# Bot commands (in-process, mocked WeiLink)
# ------------------------------------------------------------------


class TestCLILogin:
    """Tests for `weilink login`."""

    @patch("weilink.cli._make_client")
    def test_login_success_human(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.login.return_value = BotInfo(
            bot_id="bot1@im.bot",
            base_url="https://api.example.com",
            token="tok",
            user_id="user1@im.wechat",
        )
        mock_mk.return_value = wl

        cli_main(["login"])
        out = capsys.readouterr().out
        assert "Login successful" in out
        assert "bot1@im.bot" in out
        assert "user1@im.wechat" in out

    @patch("weilink.cli._make_client")
    def test_login_success_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.login.return_value = BotInfo(
            bot_id="bot1@im.bot",
            base_url="https://api.example.com",
            token="tok",
            user_id="user1@im.wechat",
        )
        mock_mk.return_value = wl

        cli_main(["login", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["success"] is True
        assert data["bot_id"] == "bot1@im.bot"

    @patch("weilink.cli._make_client")
    def test_login_failure_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.login.side_effect = RuntimeError("QR expired")
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["login", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "error" in data
        assert "QR expired" in data["error"]

    @patch("weilink.cli._make_client")
    def test_login_with_session_name(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.login.return_value = BotInfo(
            bot_id="bot2@im.bot",
            base_url="https://api.example.com",
            token="tok",
            user_id="user2@im.wechat",
        )
        mock_mk.return_value = wl

        cli_main(["login", "work", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["session"] == "work"
        wl.login.assert_called_once_with(name="work", force=False)

    @patch("weilink.cli._make_client")
    def test_login_force(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.login.return_value = BotInfo(
            bot_id="bot1@im.bot",
            base_url="https://api.example.com",
            token="tok",
        )
        mock_mk.return_value = wl

        cli_main(["login", "--force", "--json"])
        wl.login.assert_called_once_with(name=None, force=True)


class TestCLILogout:
    """Tests for `weilink logout`."""

    @patch("weilink.cli._make_client")
    def test_logout_success_human(self, mock_mk, capsys):
        wl = _make_mock_client()
        mock_mk.return_value = wl

        cli_main(["logout"])
        out = capsys.readouterr().out
        assert "logged out" in out
        assert "default" in out

    @patch("weilink.cli._make_client")
    def test_logout_success_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        mock_mk.return_value = wl

        cli_main(["logout", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["success"] is True
        assert data["session"] == "default"

    @patch("weilink.cli._make_client")
    def test_logout_failure_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.logout.side_effect = KeyError("Session 'x' not found")
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["logout", "x", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "error" in data

    @patch("weilink.cli._make_client")
    def test_logout_named_session(self, mock_mk, capsys):
        wl = _make_mock_client()
        mock_mk.return_value = wl

        cli_main(["logout", "work", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["session"] == "work"
        wl.logout.assert_called_once_with(name="work")


class TestCLIStatus:
    """Tests for `weilink status`."""

    @patch("weilink.cli._make_client")
    def test_status_human(self, mock_mk, capsys):
        sessions = {
            "default": _make_mock_session("default", connected=True, is_default=True),
            "work": _make_mock_session(
                "work",
                bot_id="bot2@im.bot",
                connected=True,
                is_default=False,
            ),
        }
        wl = _make_mock_client(sessions=sessions)
        mock_mk.return_value = wl

        cli_main(["status"])
        out = capsys.readouterr().out
        assert "connected" in out
        assert "default" in out

    @patch("weilink.cli._make_client")
    def test_status_json(self, mock_mk, capsys):
        sessions = {
            "default": _make_mock_session("default", connected=True, is_default=True),
        }
        wl = _make_mock_client(sessions=sessions)
        mock_mk.return_value = wl

        cli_main(["status", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "default"
        assert data[0]["connected"] is True

    @patch("weilink.cli._make_client")
    def test_status_empty(self, mock_mk, capsys):
        wl = _make_mock_client(sessions={})
        mock_mk.return_value = wl

        cli_main(["status"])
        out = capsys.readouterr().out
        assert "No sessions found" in out


class TestCLIRecv:
    """Tests for `weilink recv`."""

    @patch("weilink.cli._make_client")
    def test_recv_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        msg = Message(
            from_user="user1@im.wechat",
            msg_type=MessageType.TEXT,
            text="hello",
            timestamp=1711800000000,
            message_id=1,
            bot_id="bot1@im.bot",
        )
        wl.recv.return_value = [msg]
        mock_mk.return_value = wl

        cli_main(["recv", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["text"] == "hello"

    @patch("weilink.cli._make_client")
    def test_recv_human(self, mock_mk, capsys):
        wl = _make_mock_client()
        msg = Message(
            from_user="user1@im.wechat",
            msg_type=MessageType.TEXT,
            text="world",
            timestamp=1711800000000,
            message_id=2,
            bot_id="bot1@im.bot",
        )
        wl.recv.return_value = [msg]
        mock_mk.return_value = wl

        cli_main(["recv"])
        out = capsys.readouterr().out
        assert "user1@im.wechat" in out
        assert "world" in out
        assert "1 message(s) received" in out

    @patch("weilink.cli._make_client")
    def test_recv_empty(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.recv.return_value = []
        mock_mk.return_value = wl

        cli_main(["recv"])
        out = capsys.readouterr().out
        assert "No new messages" in out

    @patch("weilink.cli._make_client")
    def test_recv_timeout_arg(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.recv.return_value = []
        mock_mk.return_value = wl

        cli_main(["recv", "--timeout", "10"])
        wl.recv.assert_called_once_with(timeout=10.0)

    @patch("weilink.cli._make_client")
    def test_recv_failure_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.recv.side_effect = RuntimeError("Not connected")
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["recv", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "error" in data


class TestCLISend:
    """Tests for `weilink send`."""

    @patch("weilink.cli._make_client")
    def test_send_text_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.send.return_value = SendResult(success=True, messages=[], remaining=5)
        mock_mk.return_value = wl

        cli_main(["send", "user1@im.wechat", "--text", "hi", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["success"] is True
        wl.send.assert_called_once_with("user1@im.wechat", text="hi")

    @patch("weilink.cli._make_client")
    def test_send_text_human(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.send.return_value = SendResult(success=True, messages=[], remaining=5)
        mock_mk.return_value = wl

        cli_main(["send", "user1@im.wechat", "--text", "hi"])
        out = capsys.readouterr().out
        assert "Message sent" in out

    @patch("weilink.cli._make_client")
    def test_send_no_content(self, mock_mk, capsys):
        wl = _make_mock_client()
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["send", "user1@im.wechat"])
        err = capsys.readouterr().err
        assert "at least one" in err

    @patch("weilink.cli._make_client")
    def test_send_image(self, mock_mk, capsys, tmp_path):
        wl = _make_mock_client()
        wl.send.return_value = SendResult(success=True, messages=[], remaining=5)
        mock_mk.return_value = wl

        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xe0")

        cli_main(["send", "user1@im.wechat", "--image", str(img_file), "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["success"] is True
        call_kwargs = wl.send.call_args
        assert call_kwargs[1]["image"] == b"\xff\xd8\xff\xe0"

    @patch("weilink.cli._make_client")
    def test_send_failure_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.send.side_effect = RuntimeError("Quota exhausted")
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["send", "user1@im.wechat", "--text", "x", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "error" in data
        assert "Quota" in data["error"]


class TestCLIDownload:
    """Tests for `weilink download`."""

    @patch("weilink.cli._make_client")
    def test_download_success(self, mock_mk, capsys, tmp_path):
        wl = _make_mock_client()
        store = MagicMock()
        msg = Message(
            from_user="user1@im.wechat",
            msg_type=MessageType.IMAGE,
            timestamp=1000,
            message_id=42,
            bot_id="bot1@im.bot",
        )
        store.get_by_id.return_value = msg
        wl._message_store = store
        wl.download.return_value = b"\xff\xd8\xff\xe0"
        mock_mk.return_value = wl

        cli_main(["download", "42", "--output", str(tmp_path), "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "path" in data
        assert data["size"] == 4
        assert (tmp_path / "42.jpg").exists()

    @patch("weilink.cli._make_client")
    def test_download_no_store(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl._message_store = None
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["download", "42", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "error" in data
        assert "store" in data["error"].lower()

    @patch("weilink.cli._make_client")
    def test_download_not_found(self, mock_mk, capsys):
        wl = _make_mock_client()
        store = MagicMock()
        store.get_by_id.return_value = None
        wl._message_store = store
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["download", "999", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "error" in data
        assert "not found" in data["error"]


class TestCLIHistory:
    """Tests for `weilink history`."""

    @patch("weilink.cli._make_client")
    def test_history_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        store = MagicMock()
        store.count.return_value = 1
        store.query.return_value = [
            {"text": "hello", "msg_type": "TEXT", "direction": "received"}
        ]
        wl._message_store = store
        mock_mk.return_value = wl

        cli_main(["history", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["total"] == 1
        assert len(data["messages"]) == 1

    @patch("weilink.cli._make_client")
    def test_history_human(self, mock_mk, capsys):
        wl = _make_mock_client()
        store = MagicMock()
        store.count.return_value = 2
        store.query.return_value = [
            {
                "text": "hello",
                "msg_type": "TEXT",
                "direction": "received",
                "timestamp": "2026-03-30",
                "from_user": "user1",
            },
            {
                "text": "world",
                "msg_type": "TEXT",
                "direction": "sent",
                "timestamp": "2026-03-30",
                "from_user": "bot1",
            },
        ]
        wl._message_store = store
        mock_mk.return_value = wl

        cli_main(["history"])
        out = capsys.readouterr().out
        assert "hello" in out
        assert "Showing 2 of 2 message(s)" in out

    @patch("weilink.cli._make_client")
    def test_history_no_store(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl._message_store = None
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["history", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "error" in data

    @patch("weilink.cli._make_client")
    def test_history_with_filters(self, mock_mk, capsys):
        wl = _make_mock_client()
        store = MagicMock()
        store.count.return_value = 0
        store.query.return_value = []
        wl._message_store = store
        mock_mk.return_value = wl

        cli_main(
            [
                "history",
                "--user",
                "user1@im.wechat",
                "--type",
                "TEXT",
                "--direction",
                "received",
                "--limit",
                "10",
                "--offset",
                "5",
                "--json",
            ]
        )
        # Verify count/query were called with filters
        call_kwargs = store.count.call_args[1]
        assert call_kwargs["user_id"] == "user1@im.wechat"
        assert call_kwargs["msg_type"] == MessageType.TEXT.value
        assert call_kwargs["direction"] == 1

        q_kwargs = store.query.call_args[1]
        assert q_kwargs["limit"] == 10
        assert q_kwargs["offset"] == 5

    @patch("weilink.cli._make_client")
    def test_history_empty(self, mock_mk, capsys):
        wl = _make_mock_client()
        store = MagicMock()
        store.count.return_value = 0
        store.query.return_value = []
        wl._message_store = store
        mock_mk.return_value = wl

        cli_main(["history"])
        out = capsys.readouterr().out
        assert "No messages found" in out


class TestCLISessions:
    """Tests for `weilink sessions` (list / rename / default)."""

    @patch("weilink.cli._make_client")
    def test_sessions_list_json(self, mock_mk, capsys):
        sessions = {
            "default": _make_mock_session("default", connected=True),
            "work": _make_mock_session(
                "work", bot_id="bot2@im.bot", connected=True, is_default=False
            ),
        }
        wl = _make_mock_client(sessions=sessions)
        mock_mk.return_value = wl

        cli_main(["sessions", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 2

    @patch("weilink.cli._make_client")
    def test_sessions_rename_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        mock_mk.return_value = wl

        cli_main(["sessions", "rename", "default", "main", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["success"] is True
        assert data["old_name"] == "default"
        assert data["new_name"] == "main"
        wl.rename_session.assert_called_once_with("default", "main")

    @patch("weilink.cli._make_client")
    def test_sessions_rename_human(self, mock_mk, capsys):
        wl = _make_mock_client()
        mock_mk.return_value = wl

        cli_main(["sessions", "rename", "default", "main"])
        out = capsys.readouterr().out
        assert "renamed" in out
        assert "main" in out

    @patch("weilink.cli._make_client")
    def test_sessions_rename_error(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.rename_session.side_effect = ValueError("Name conflict")
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["sessions", "rename", "a", "b", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "error" in data

    @patch("weilink.cli._make_client")
    def test_sessions_default_json(self, mock_mk, capsys):
        wl = _make_mock_client()
        mock_mk.return_value = wl

        cli_main(["sessions", "default", "work", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["success"] is True
        assert data["default_session"] == "work"
        wl.set_default.assert_called_once_with("work")

    @patch("weilink.cli._make_client")
    def test_sessions_default_human(self, mock_mk, capsys):
        wl = _make_mock_client()
        mock_mk.return_value = wl

        cli_main(["sessions", "default", "work"])
        out = capsys.readouterr().out
        assert "Default session set" in out
        assert "work" in out

    @patch("weilink.cli._make_client")
    def test_sessions_default_error(self, mock_mk, capsys):
        wl = _make_mock_client()
        wl.set_default.side_effect = KeyError("Session 'x' not found")
        mock_mk.return_value = wl

        with pytest.raises(SystemExit, match="1"):
            cli_main(["sessions", "default", "x", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "error" in data
