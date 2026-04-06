"""Tests for admin panel server and API handlers."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from weilink import WeiLink
from weilink.models import Message, MessageType


def _kill_proc(proc: subprocess.Popen) -> None:
    """Terminate a subprocess, falling back to SIGKILL if it won't die."""
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture()
def wl(tmp_path):
    """Create a WeiLink client with temp base_path."""
    return WeiLink(base_path=tmp_path)


class TestAdminServer:
    """Tests for AdminServer lifecycle."""

    def test_start_and_stop(self, wl):
        info = wl.start_admin(port=0)
        assert info.port > 0
        assert "http://localhost:" in info.url
        wl.stop_admin()

    def test_start_returns_existing_info(self, wl):
        info1 = wl.start_admin(port=0)
        info2 = wl.start_admin(port=0)
        assert info1.port == info2.port
        wl.stop_admin()

    def test_close_stops_admin(self, wl):
        wl.start_admin(port=0)
        wl.close()
        assert wl._admin_server is None

    def test_stop_admin_when_not_running(self, wl):
        wl.stop_admin()  # should not raise


class TestAdminCLI:
    """Tests for standalone weilink-admin CLI entry point."""

    def test_cli_starts_and_responds(self, tmp_path):
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
            # Read the "Admin panel:" line to get the URL
            assert proc.stdout is not None
            url = None
            for _ in range(50):
                line = proc.stdout.readline()
                if "Admin panel:" in line:
                    url = line.strip().split()[-1]
                    break
            assert url is not None, "CLI did not print the URL"

            # Verify the server is actually responding
            req = urllib.request.Request(url + "/api/status")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            assert "version" in data
        finally:
            _kill_proc(proc)

    def test_cli_custom_base_path_printed(self, tmp_path):
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
            lines = []
            for _ in range(50):
                line = proc.stdout.readline()
                lines.append(line)
                if "Data:" in line:
                    break
            assert any(str(tmp_path) in ln for ln in lines)
        finally:
            _kill_proc(proc)

    def test_cli_sigterm_graceful_shutdown(self, tmp_path):
        import signal

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
        # Wait for startup
        assert proc.stdout is not None
        for _ in range(50):
            line = proc.stdout.readline()
            if "Admin panel:" in line:
                break

        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        assert proc.returncode is not None


class TestAdminAPI:
    """Tests for admin REST API endpoints."""

    @pytest.fixture(autouse=True)
    def _start_server(self, wl):
        self.info = wl.start_admin(port=0)
        self.wl = wl
        self.base = self.info.url
        yield
        wl.stop_admin()

    def _get(self, path):
        req = urllib.request.Request(self.base + path)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _post(self, path, data=None):
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(
            self.base + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def test_root_serves_html(self):
        req = urllib.request.Request(self.base + "/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode()
            assert "WeiLink Admin" in content
            assert "<html" in content

    def test_api_status(self):
        data = self._get("/api/status")
        assert "version" in data
        assert data["is_connected"] is False
        assert data["session_count"] == 1  # default session

    def test_api_sessions_default(self):
        data = self._get("/api/sessions")
        sessions = data["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["name"] == "default"
        assert sessions[0]["connected"] is False
        assert sessions[0]["users"] == []

    def test_api_sessions_with_context(self, tmp_path):
        # Inject a context token into the default session
        s = self.wl._sessions["default"]
        s.context_tokens["user1@im.wechat"] = "tok123"
        s.context_timestamps["user1@im.wechat"] = time.time()

        data = self._get("/api/sessions")
        session = data["sessions"][0]
        assert session["user_count"] == 1
        assert session["users"][0]["user_id"] == "user1@im.wechat"
        assert session["users"][0]["fresh"] is True

    def test_api_logout_nonexistent(self):
        try:
            self._post("/api/sessions/nonexistent/logout")
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_api_rename_missing_new_name(self):
        try:
            self._post("/api/sessions/default/rename", {})
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_locale_en(self):
        data = self._get("/locales/en.json")
        assert "app" in data
        assert data["app"]["title"] == "WeiLink Admin"

    def test_locale_zh(self):
        data = self._get("/locales/zh.json")
        assert "app" in data

    def test_locale_not_found(self):
        try:
            self._get("/locales/xx.json")
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_api_sessions_has_is_default(self):
        data = self._get("/api/sessions")
        session = data["sessions"][0]
        assert "is_default" in session
        assert session["is_default"] is True

    def test_api_set_default(self, tmp_path):
        from weilink.client import _Session
        from weilink.models import BotInfo

        s2 = _Session(
            name="zb",
            token_path=tmp_path / "zb" / "token.json",
            bot_info=BotInfo(
                bot_id="zb@im.bot",
                base_url="https://example.com",
                token="tok_zb",
            ),
        )
        self.wl._sessions["zb"] = s2

        data = self._post("/api/set-default", {"name": "zb"})
        assert data["success"] is True
        assert self.wl.bot_id == "zb@im.bot"

    def test_api_set_default_nonexistent(self):
        try:
            self._post("/api/set-default", {"name": "nope"})
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_api_set_default_missing_name(self):
        try:
            self._post("/api/set-default", {})
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_not_found(self):
        try:
            self._get("/api/nonexistent")
        except urllib.error.HTTPError as e:
            assert e.code == 404


class TestAdminMessages:
    """Tests for GET /api/messages endpoint."""

    @pytest.fixture(autouse=True)
    def _start_server(self, tmp_path):
        self.wl = WeiLink(base_path=tmp_path, message_store=True)
        self.info = self.wl.start_admin(port=0)
        self.base = self.info.url
        yield
        self.wl.stop_admin()
        self.wl.close()

    def _get(self, path):
        req = urllib.request.Request(self.base + path)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _get_error(self, path):
        try:
            self._get(path)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
        return None, None

    def _seed_messages(self, count=5, user_id="u1@im.wechat", bot_id="b1@im.bot"):
        """Insert test messages into the store."""
        store = self.wl._message_store
        now_ms = int(time.time() * 1000)
        msgs = []
        for i in range(count):
            msgs.append(
                Message(
                    from_user=user_id,
                    msg_type=MessageType.TEXT,
                    text=f"message {i}",
                    timestamp=now_ms - (count - i) * 60000,
                    message_id=1000 + i,
                    bot_id=bot_id,
                )
            )
        store.store(msgs, direction=1)
        return msgs

    def test_messages_returns_results(self):
        self._seed_messages(3)
        data = self._get("/api/messages?user_id=u1@im.wechat")
        assert data["total"] == 3
        assert len(data["messages"]) == 3

    def test_messages_pagination(self):
        self._seed_messages(10)
        data = self._get("/api/messages?user_id=u1@im.wechat&limit=3&offset=0")
        assert data["total"] == 10
        assert len(data["messages"]) == 3

        data2 = self._get("/api/messages?user_id=u1@im.wechat&limit=3&offset=3")
        assert len(data2["messages"]) == 3
        # Should be different messages
        ids1 = {m["message_id"] for m in data["messages"]}
        ids2 = {m["message_id"] for m in data2["messages"]}
        assert ids1.isdisjoint(ids2)

    def test_messages_filter_by_type(self):
        store = self.wl._message_store
        now_ms = int(time.time() * 1000)
        store.store(
            [
                Message(
                    from_user="u1@im.wechat",
                    msg_type=MessageType.TEXT,
                    text="hello",
                    timestamp=now_ms,
                    message_id=2001,
                    bot_id="b1@im.bot",
                ),
                Message(
                    from_user="u1@im.wechat",
                    msg_type=MessageType.IMAGE,
                    timestamp=now_ms + 1000,
                    message_id=2002,
                    bot_id="b1@im.bot",
                ),
            ],
            direction=1,
        )
        data = self._get("/api/messages?user_id=u1@im.wechat&msg_type=1")
        assert data["total"] == 1
        assert data["messages"][0]["msg_type"] == "TEXT"

    def test_messages_filter_by_text(self):
        self._seed_messages(5)
        data = self._get("/api/messages?user_id=u1@im.wechat&text_contains=message%202")
        assert data["total"] == 1
        assert "message 2" in data["messages"][0]["text"]

    def test_messages_direction_field(self):
        self._seed_messages(1)
        data = self._get("/api/messages?user_id=u1@im.wechat")
        assert data["messages"][0]["direction"] == "received"

    def test_messages_empty_result(self):
        data = self._get("/api/messages?user_id=nobody@im.wechat")
        assert data["total"] == 0
        assert data["messages"] == []

    def test_messages_limit_capped_at_200(self):
        self._seed_messages(5)
        data = self._get("/api/messages?user_id=u1@im.wechat&limit=999")
        # Should not error; limit is capped at 200 internally
        assert len(data["messages"]) == 5

    def test_download_media_not_found(self):
        try:
            req = urllib.request.Request(self.base + "/api/messages/999999/download")
            urllib.request.urlopen(req, timeout=5)
            pytest.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_download_media_text_message(self):
        """TEXT messages have no downloadable media."""
        self._seed_messages(1)
        msg_id = 1000  # first seeded message_id
        try:
            req = urllib.request.Request(self.base + f"/api/messages/{msg_id}/download")
            urllib.request.urlopen(req, timeout=5)
            pytest.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 400


class TestAdminMessagesDisabled:
    """Tests for /api/messages when message_store is disabled."""

    @pytest.fixture(autouse=True)
    def _start_server(self, tmp_path):
        self.wl = WeiLink(base_path=tmp_path)  # no message_store
        self.info = self.wl.start_admin(port=0)
        self.base = self.info.url
        yield
        self.wl.stop_admin()

    def test_messages_returns_400_when_disabled(self):
        try:
            req = urllib.request.Request(self.base + "/api/messages")
            urllib.request.urlopen(req, timeout=5)
            pytest.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read())
            assert "not enabled" in body["error"]

    def test_download_media_returns_400_when_disabled(self):
        try:
            req = urllib.request.Request(self.base + "/api/messages/12345/download")
            urllib.request.urlopen(req, timeout=5)
            pytest.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 400


class TestAdminSend:
    """Tests for POST /api/send endpoint."""

    @pytest.fixture(autouse=True)
    def _start_server(self, wl):
        self.info = wl.start_admin(port=0)
        self.wl = wl
        self.base = self.info.url
        yield
        wl.stop_admin()

    def _post(self, path, data=None):
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(
            self.base + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def test_send_missing_to(self):
        """POST /api/send without 'to' returns 400."""
        try:
            self._post("/api/send", {"text": "hello"})
            pytest.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read())
            assert "to" in body["error"].lower()

    def test_send_empty_body(self):
        """POST /api/send with empty body returns 400."""
        try:
            self._post("/api/send", {})
            pytest.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_send_no_content(self):
        """POST /api/send with 'to' but no text/media returns 400."""
        try:
            self._post("/api/send", {"to": "user@im.wechat"})
            pytest.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read())
            assert "text" in body["error"].lower() or "media" in body["error"].lower()

    def test_send_invalid_base64(self):
        """POST /api/send with invalid base64 for media returns 400."""
        try:
            self._post(
                "/api/send", {"to": "user@im.wechat", "image": "not-valid-b64!!!"}
            )
            pytest.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read())
            assert "base64" in body["error"].lower()

    def test_send_not_logged_in(self):
        """POST /api/send when not logged in returns error."""
        try:
            self._post("/api/send", {"to": "user@im.wechat", "text": "hello"})
            pytest.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 400
