"""Tests for weilink data models."""

from weilink.models import BotInfo, Message, MessageType, _UpdatesResponse


class TestMessageType:
    def test_values(self):
        assert MessageType.TEXT == 1
        assert MessageType.IMAGE == 2
        assert MessageType.VOICE == 3
        assert MessageType.FILE == 4
        assert MessageType.VIDEO == 5

    def test_from_int(self):
        assert MessageType(1) == MessageType.TEXT
        assert MessageType(5) == MessageType.VIDEO


class TestBotInfo:
    def test_creation(self):
        info = BotInfo(bot_id="abc@im.bot", base_url="https://example.com", token="tok")
        assert info.bot_id == "abc@im.bot"
        assert info.base_url == "https://example.com"
        assert info.token == "tok"

    def test_frozen(self):
        info = BotInfo(bot_id="abc@im.bot", base_url="https://example.com", token="tok")
        try:
            info.bot_id = "other"  # type: ignore[misc]
            assert False, "Should not allow mutation"
        except AttributeError:
            pass


class TestMessage:
    def test_defaults(self):
        msg = Message(from_user="user@im.wechat")
        assert msg.from_user == "user@im.wechat"
        assert msg.text is None
        assert msg.msg_type == MessageType.TEXT
        assert msg.timestamp == 0
        assert msg.message_id is None
        assert msg.context_token == ""

    def test_with_text(self):
        msg = Message(
            from_user="user@im.wechat",
            text="hello",
            msg_type=MessageType.TEXT,
            timestamp=1234567890,
            message_id=42,
            context_token="ctx123",
        )
        assert msg.text == "hello"
        assert msg.timestamp == 1234567890
        assert msg.message_id == 42
        assert msg.context_token == "ctx123"

    def test_frozen(self):
        msg = Message(from_user="user@im.wechat")
        try:
            msg.text = "modified"  # type: ignore[misc]
            assert False, "Should not allow mutation"
        except AttributeError:
            pass


class TestUpdatesResponse:
    def test_defaults(self):
        resp = _UpdatesResponse()
        assert resp.ret == 0
        assert resp.errcode is None
        assert resp.msgs == []
        assert resp.get_updates_buf == ""
