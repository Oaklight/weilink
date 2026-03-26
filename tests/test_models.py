"""Tests for weilink data models."""

from weilink.models import (
    BotInfo,
    FileInfo,
    ImageInfo,
    Message,
    MessageType,
    RefMessage,
    VideoInfo,
    VoiceInfo,
    _UpdatesResponse,
)


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
            info.bot_id = "other"
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
            msg.text = "modified"
            assert False, "Should not allow mutation"
        except AttributeError:
            pass


class TestRefMessageToDict:
    def test_text(self):
        ref = RefMessage(msg_type=MessageType.TEXT, text="quoted")
        d = ref.to_dict()
        assert d == {"msg_type": "TEXT", "text": "quoted"}

    def test_image(self):
        ref = RefMessage(
            msg_type=MessageType.IMAGE,
            image=ImageInfo(url="http://img", thumb_width=100, thumb_height=80),
        )
        d = ref.to_dict()
        assert d["msg_type"] == "IMAGE"
        assert d["image"]["url"] == "http://img"
        assert d["image"]["thumb_width"] == 100

    def test_empty_fields_omitted(self):
        ref = RefMessage(msg_type=MessageType.TEXT)
        d = ref.to_dict()
        assert "text" not in d
        assert "image" not in d


class TestMessageToDict:
    def test_text_message(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.TEXT,
            text="hello",
            timestamp=1000,
            message_id=1,
            bot_id="b@im.bot",
        )
        d = msg.to_dict()
        assert d["from_user"] == "u@im.wechat"
        assert d["msg_type"] == "TEXT"
        assert d["text"] == "hello"
        assert d["timestamp"] == 1000
        assert d["message_id"] == 1
        assert d["bot_id"] == "b@im.bot"

    def test_image_message(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.IMAGE,
            image=ImageInfo(url="http://img", thumb_width=200, thumb_height=150),
        )
        d = msg.to_dict()
        assert d["image"]["url"] == "http://img"
        assert "text" not in d

    def test_voice_message(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.VOICE,
            voice=VoiceInfo(playtime=3000, text="transcription"),
        )
        d = msg.to_dict()
        assert d["voice"]["playtime"] == 3000
        assert d["voice"]["text"] == "transcription"

    def test_file_message(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.FILE,
            file=FileInfo(file_name="doc.pdf", file_size="1024"),
        )
        d = msg.to_dict()
        assert d["file"]["file_name"] == "doc.pdf"

    def test_video_message(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.VIDEO,
            video=VideoInfo(play_length=10, thumb_width=320, thumb_height=240),
        )
        d = msg.to_dict()
        assert d["video"]["play_length"] == 10

    def test_with_ref_msg(self):
        msg = Message(
            from_user="u@im.wechat",
            text="reply",
            ref_msg=RefMessage(msg_type=MessageType.TEXT, text="original"),
        )
        d = msg.to_dict()
        assert d["ref_msg"] == {"msg_type": "TEXT", "text": "original"}

    def test_none_fields_omitted(self):
        msg = Message(from_user="u@im.wechat")
        d = msg.to_dict()
        assert "text" not in d
        assert "image" not in d
        assert "ref_msg" not in d


class TestUpdatesResponse:
    def test_defaults(self):
        resp = _UpdatesResponse()
        assert resp.ret == 0
        assert resp.errcode is None
        assert resp.msgs == []
        assert resp.get_updates_buf == ""
