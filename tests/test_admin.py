"""Tests for admin panel server and API handlers."""

import json
import time
import urllib.error
import urllib.request

import pytest

from weilink import WeiLink


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

    def test_not_found(self):
        try:
            self._get("/api/nonexistent")
        except urllib.error.HTTPError as e:
            assert e.code == 404
