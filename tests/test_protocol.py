"""Tests for weilink internal protocol module."""

import base64

from weilink._protocol import (
    BASE_URL,
    BOT_TYPE,
    CHANNEL_VERSION,
    EP_GET_UPDATES,
    EP_QR_CODE,
    EP_SEND_MESSAGE,
    SESSION_EXPIRED,
    _make_headers,
    _random_uin,
)


class TestRandomUin:
    def test_returns_base64_string(self):
        uin = _random_uin()
        # Should be valid base64
        decoded = base64.b64decode(uin).decode()
        # Should be a numeric string
        assert decoded.isdigit()

    def test_different_each_call(self):
        values = {_random_uin() for _ in range(10)}
        # Extremely unlikely to have duplicates in 10 calls
        assert len(values) > 1


class TestMakeHeaders:
    def test_without_token(self):
        headers = _make_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["AuthorizationType"] == "ilink_bot_token"
        assert "X-WECHAT-UIN" in headers
        assert "Authorization" not in headers

    def test_with_token(self):
        headers = _make_headers(token="my_token")
        assert headers["Authorization"] == "Bearer my_token"
        assert headers["Content-Type"] == "application/json"


class TestConstants:
    def test_base_url(self):
        assert BASE_URL == "https://ilinkai.weixin.qq.com"

    def test_bot_type(self):
        assert BOT_TYPE == 3

    def test_channel_version(self):
        assert CHANNEL_VERSION == "1.0.2"

    def test_session_expired(self):
        assert SESSION_EXPIRED == -14

    def test_endpoints(self):
        assert EP_QR_CODE.startswith("/ilink/bot/")
        assert EP_GET_UPDATES.startswith("/ilink/bot/")
        assert EP_SEND_MESSAGE.startswith("/ilink/bot/")
