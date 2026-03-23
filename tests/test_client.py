"""Tests for WeiLink client."""

import json
import tempfile
from pathlib import Path

from weilink.client import WeiLink
from weilink.models import BotInfo, MessageType


class TestWeiLinkInit:
    def test_default_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            wl = WeiLink(token_path=token_path)
            assert not wl.is_connected
            assert wl.bot_id is None

    def test_load_existing_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            token_path.write_text(
                json.dumps(
                    {
                        "bot_id": "test@im.bot",
                        "base_url": "https://example.com",
                        "token": "test_token",
                        "cursor": "cursor_abc",
                    }
                )
            )
            wl = WeiLink(token_path=token_path)
            assert wl.is_connected
            assert wl.bot_id == "test@im.bot"

    def test_corrupted_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            token_path.write_text("not json")
            wl = WeiLink(token_path=token_path)
            assert not wl.is_connected


class TestWeiLinkSend:
    def test_send_without_login(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            try:
                wl.send("user@im.wechat", "hello")
                assert False, "Should raise RuntimeError"
            except RuntimeError:
                pass

    def test_send_without_context_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            token_path.write_text(
                json.dumps(
                    {
                        "bot_id": "test@im.bot",
                        "base_url": "https://example.com",
                        "token": "test_token",
                    }
                )
            )
            wl = WeiLink(token_path=token_path)
            result = wl.send("unknown_user@im.wechat", "hello")
            assert result is False


class TestWeiLinkRecv:
    def test_recv_without_login(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            try:
                wl.recv()
                assert False, "Should raise RuntimeError"
            except RuntimeError:
                pass


class TestWeiLinkPersistence:
    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "sub" / "token.json"

            wl = WeiLink(token_path=token_path)
            wl._bot_info = BotInfo(
                bot_id="test@im.bot",
                base_url="https://example.com",
                token="tok123",
            )
            wl._cursor = "cursor_xyz"
            wl._save_state()

            # Reload
            wl2 = WeiLink(token_path=token_path)
            assert wl2.is_connected
            assert wl2.bot_id == "test@im.bot"
            assert wl2._cursor == "cursor_xyz"


class TestWeiLinkContextManager:
    def test_context_manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            with WeiLink(token_path=token_path) as wl:
                assert not wl.is_connected


class TestParseMessage:
    def test_parse_text_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            raw = {
                "from_user_id": "user@im.wechat",
                "to_user_id": "bot@im.bot",
                "message_type": 1,
                "message_state": 2,
                "context_token": "ctx_abc",
                "create_time_ms": 1700000000000,
                "message_id": 99,
                "item_list": [{"type": 1, "text_item": {"text": "hello world"}}],
            }
            msg = wl._parse_message(raw)
            assert msg is not None
            assert msg.from_user == "user@im.wechat"
            assert msg.text == "hello world"
            assert msg.msg_type == MessageType.TEXT
            assert msg.timestamp == 1700000000000
            assert msg.message_id == 99
            assert msg.context_token == "ctx_abc"

    def test_parse_image_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            raw = {
                "from_user_id": "user@im.wechat",
                "message_type": 1,
                "context_token": "ctx_img",
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {
                            "media": {
                                "encrypt_query_param": "param123",
                                "aes_key": "abc",
                                "encrypt_type": 1,
                            },
                            "url": "https://example.com/img.jpg",
                            "thumb_width": 100,
                            "thumb_height": 200,
                        },
                    }
                ],
            }
            msg = wl._parse_message(raw)
            assert msg is not None
            assert msg.msg_type == MessageType.IMAGE
            assert msg.text is None
            assert msg.image is not None
            assert msg.image.media.encrypt_query_param == "param123"
            assert msg.image.media.aes_key == "abc"
            assert msg.image.url == "https://example.com/img.jpg"
            assert msg.image.thumb_width == 100

    def test_parse_voice_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            raw = {
                "from_user_id": "user@im.wechat",
                "message_type": 1,
                "context_token": "ctx_voice",
                "item_list": [
                    {
                        "type": 3,
                        "voice_item": {
                            "media": {"aes_key": "voicekey"},
                            "playtime": 5,
                            "text": "hello from voice",
                        },
                    }
                ],
            }
            msg = wl._parse_message(raw)
            assert msg is not None
            assert msg.msg_type == MessageType.VOICE
            assert msg.voice is not None
            assert msg.voice.playtime == 5
            assert msg.voice.text == "hello from voice"

    def test_parse_file_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            raw = {
                "from_user_id": "user@im.wechat",
                "message_type": 1,
                "context_token": "ctx_file",
                "item_list": [
                    {
                        "type": 4,
                        "file_item": {
                            "media": {"aes_key": "filekey"},
                            "file_name": "doc.pdf",
                            "len": "12345",
                            "md5": "abc123",
                        },
                    }
                ],
            }
            msg = wl._parse_message(raw)
            assert msg is not None
            assert msg.msg_type == MessageType.FILE
            assert msg.file is not None
            assert msg.file.file_name == "doc.pdf"
            assert msg.file.file_size == "12345"
            assert msg.file.md5 == "abc123"

    def test_parse_video_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            raw = {
                "from_user_id": "user@im.wechat",
                "message_type": 1,
                "context_token": "ctx_video",
                "item_list": [
                    {
                        "type": 5,
                        "video_item": {
                            "media": {"aes_key": "vidkey"},
                            "play_length": 30,
                            "video_md5": "vid123",
                            "thumb_width": 640,
                            "thumb_height": 480,
                        },
                    }
                ],
            }
            msg = wl._parse_message(raw)
            assert msg is not None
            assert msg.msg_type == MessageType.VIDEO
            assert msg.video is not None
            assert msg.video.play_length == 30
            assert msg.video.thumb_width == 640

    def test_parse_empty_from(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            raw = {"from_user_id": "", "item_list": []}
            msg = wl._parse_message(raw)
            assert msg is None
