"""Tests for WeiLink client."""

import json
import tempfile
import time
from pathlib import Path

from weilink.client import WeiLink
from weilink.models import BotInfo, MessageType, UploadMediaType, UploadedMedia


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
            assert not result


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


class TestContextPersistence:
    """Tests for experimental context_tokens persistence (contexts.json)."""

    def test_save_and_load_contexts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            contexts_path = Path(tmpdir) / "contexts.json"

            wl = WeiLink(token_path=token_path)
            now = time.time()
            wl._context_tokens = {"user1@im.wechat": "ctx_tok_1"}
            wl._context_timestamps = {"user1@im.wechat": now}
            wl._save_contexts()

            assert contexts_path.exists()
            data = json.loads(contexts_path.read_text())
            assert "user1@im.wechat" in data
            assert data["user1@im.wechat"]["t"] == "ctx_tok_1"
            assert data["user1@im.wechat"]["ts"] == now

            # Reload via a new client instance
            wl2 = WeiLink(token_path=token_path)
            assert wl2._context_tokens.get("user1@im.wechat") == "ctx_tok_1"
            assert wl2._context_timestamps.get("user1@im.wechat") == now

    def test_expired_contexts_discarded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            contexts_path = Path(tmpdir) / "contexts.json"

            stale_ts = time.time() - 25 * 3600  # 25 hours ago
            fresh_ts = time.time() - 1 * 3600  # 1 hour ago
            data = {
                "stale_user@im.wechat": {"t": "old_ctx", "ts": stale_ts},
                "fresh_user@im.wechat": {"t": "new_ctx", "ts": fresh_ts},
            }
            contexts_path.write_text(json.dumps(data))

            wl = WeiLink(token_path=token_path)
            assert "stale_user@im.wechat" not in wl._context_tokens
            assert wl._context_tokens.get("fresh_user@im.wechat") == "new_ctx"

    def test_token_json_does_not_contain_context_tokens(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"

            wl = WeiLink(token_path=token_path)
            wl._bot_info = BotInfo(
                bot_id="test@im.bot",
                base_url="https://example.com",
                token="tok123",
            )
            wl._context_tokens = {"user@im.wechat": "ctx_tok"}
            wl._save_state()

            data = json.loads(token_path.read_text())
            assert "context_tokens" not in data

    def test_corrupted_contexts_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            contexts_path = Path(tmpdir) / "contexts.json"
            contexts_path.write_text("not valid json")

            # Should not raise; just logs a warning
            wl = WeiLink(token_path=token_path)
            assert wl._context_tokens == {}

    def test_contexts_path_is_sibling_of_token_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "sub" / "token.json"
            wl = WeiLink(token_path=token_path)
            assert wl._contexts_path == Path(tmpdir) / "sub" / "contexts.json"

    def test_per_user_latest_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"

            wl = WeiLink(token_path=token_path)
            now = time.time()
            wl._context_tokens = {"user@im.wechat": "first_token"}
            wl._context_timestamps = {"user@im.wechat": now - 100}
            wl._save_contexts()

            # Overwrite with a newer token
            wl._context_tokens["user@im.wechat"] = "second_token"
            wl._context_timestamps["user@im.wechat"] = now
            wl._save_contexts()

            wl2 = WeiLink(token_path=token_path)
            assert wl2._context_tokens["user@im.wechat"] == "second_token"

    def test_malformed_entry_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            contexts_path = Path(tmpdir) / "contexts.json"

            data = {
                "bad_user@im.wechat": "just_a_string",  # not a dict
                "good_user@im.wechat": {"t": "tok", "ts": time.time()},
            }
            contexts_path.write_text(json.dumps(data))

            wl = WeiLink(token_path=token_path)
            assert "bad_user@im.wechat" not in wl._context_tokens
            assert wl._context_tokens.get("good_user@im.wechat") == "tok"


class TestUploadAndReuse:
    """Tests for upload() and send() with UploadedMedia."""

    def _make_client(self, tmpdir: str) -> WeiLink:
        """Create a logged-in WeiLink client with a context_token."""
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
        wl._context_tokens["user@im.wechat"] = "ctx_tok"
        wl._context_timestamps["user@im.wechat"] = time.time()
        return wl

    def test_upload_requires_login(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            try:
                wl.upload("user@im.wechat", b"data", "image")
                assert False, "Should raise RuntimeError"
            except RuntimeError:
                pass

    def test_upload_invalid_media_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = self._make_client(tmpdir)
            try:
                wl.upload("user@im.wechat", b"data", "pdf")
                assert False, "Should raise ValueError"
            except ValueError as e:
                assert "pdf" in str(e)

    def test_upload_file_requires_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = self._make_client(tmpdir)
            try:
                wl.upload("user@im.wechat", b"data", "file")
                assert False, "Should raise ValueError"
            except ValueError as e:
                assert "file_name" in str(e)

    def test_send_with_uploaded_media_no_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = self._make_client(tmpdir)
            ref = UploadedMedia(
                media_type=UploadMediaType.IMAGE,
                filekey="abc",
                download_param="param",
                aes_key_hex="0" * 32,
                file_size=100,
                cipher_size=112,
            )
            result = wl.send("unknown@im.wechat", image=ref)
            assert not result

    def test_uploaded_media_frozen(self):
        ref = UploadedMedia(
            media_type=UploadMediaType.IMAGE,
            filekey="abc",
            download_param="param",
            aes_key_hex="0" * 32,
            file_size=100,
            cipher_size=112,
        )
        try:
            ref.filekey = "xyz"
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass

    def test_uploaded_media_file_name(self):
        ref = UploadedMedia(
            media_type=UploadMediaType.FILE,
            filekey="abc",
            download_param="param",
            aes_key_hex="0" * 32,
            file_size=100,
            cipher_size=112,
            file_name="test.pdf",
        )
        assert ref.file_name == "test.pdf"
        assert ref.media_type == UploadMediaType.FILE

    def test_send_no_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = self._make_client(tmpdir)
            result = wl.send("user@im.wechat")
            assert not result


class TestMultiSession:
    """Tests for multi-session support."""

    def test_default_session_backward_compat(self):
        """Single-session usage is unchanged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            token_path.write_text(
                json.dumps(
                    {
                        "bot_id": "bot1@im.bot",
                        "base_url": "https://example.com",
                        "token": "tok1",
                    }
                )
            )
            wl = WeiLink(token_path=token_path)
            assert wl.is_connected
            assert wl.bot_id == "bot1@im.bot"
            assert list(wl.sessions) == ["default"]
            assert wl.bot_ids == {"default": "bot1@im.bot"}

    def test_bot_ids_empty_when_not_connected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            assert wl.bot_ids == {}
            assert list(wl.sessions) == ["default"]

    def test_find_session_for_user(self):
        """Auto-routing picks the session with the most recent context token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")

            # Set up two sessions manually
            wl._default_session.bot_info = BotInfo(
                bot_id="bot1@im.bot",
                base_url="https://example.com",
                token="tok1",
            )
            wl._default_session.context_tokens["user@im.wechat"] = "ctx_old"
            wl._default_session.context_timestamps["user@im.wechat"] = time.time() - 100

            from weilink.client import _Session

            session2 = _Session(
                name="second",
                token_path=Path(tmpdir) / "second" / "token.json",
                bot_info=BotInfo(
                    bot_id="bot2@im.bot",
                    base_url="https://example.com",
                    token="tok2",
                ),
            )
            session2.context_tokens["user@im.wechat"] = "ctx_new"
            session2.context_timestamps["user@im.wechat"] = time.time()
            wl._sessions["second"] = session2

            # Should pick session2 (more recent timestamp)
            found = wl._find_session_for_user("user@im.wechat")
            assert found is not None
            assert found.name == "second"

            # Unknown user returns None
            assert wl._find_session_for_user("nobody@im.wechat") is None

    def test_is_connected_any_session(self):
        """is_connected returns True if any session has credentials."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            assert not wl.is_connected

            from weilink.client import _Session

            session2 = _Session(
                name="second",
                token_path=Path(tmpdir) / "second" / "token.json",
                bot_info=BotInfo(
                    bot_id="bot2@im.bot",
                    base_url="https://example.com",
                    token="tok2",
                ),
            )
            wl._sessions["second"] = session2
            assert wl.is_connected
            # bot_id still returns default (None)
            assert wl.bot_id is None
            assert wl.bot_ids == {"second": "bot2@im.bot"}

    def test_named_session_file_isolation(self):
        """Named sessions store files in separate subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)

            session = wl._create_session("foo", Path(tmpdir) / "foo" / "token.json")
            session.bot_info = BotInfo(
                bot_id="bot_foo@im.bot",
                base_url="https://example.com",
                token="tok_foo",
            )
            session.context_tokens["user@im.wechat"] = "ctx_foo"
            session.context_timestamps["user@im.wechat"] = time.time()

            wl._save_session_state(session)
            wl._save_session_contexts(session)

            # Verify files are in the right place
            assert (Path(tmpdir) / "foo" / "token.json").exists()
            assert (Path(tmpdir) / "foo" / "contexts.json").exists()

            # Default session files should not exist (no bot_info)
            assert not (Path(tmpdir) / "token.json").exists()

    def test_message_has_bot_id(self):
        """Parsed messages include bot_id when provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")
            raw = {
                "from_user_id": "user@im.wechat",
                "message_type": 1,
                "context_token": "ctx_abc",
                "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
            }
            msg = wl._parse_message(raw, bot_id="bot1@im.bot")
            assert msg is not None
            assert msg.bot_id == "bot1@im.bot"

            # Without bot_id, defaults to None
            msg2 = wl._parse_message(raw)
            assert msg2 is not None
            assert msg2.bot_id is None

    def test_close_saves_all_sessions(self):
        """close() saves state for all sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            wl._default_session.bot_info = BotInfo(
                bot_id="bot1@im.bot",
                base_url="https://example.com",
                token="tok1",
            )

            from weilink.client import _Session

            s2 = _Session(
                name="s2",
                token_path=Path(tmpdir) / "s2" / "token.json",
                bot_info=BotInfo(
                    bot_id="bot2@im.bot",
                    base_url="https://example.com",
                    token="tok2",
                ),
            )
            wl._sessions["s2"] = s2

            wl.close()

            assert (Path(tmpdir) / "token.json").exists()
            assert (Path(tmpdir) / "s2" / "token.json").exists()

    def test_base_path_constructor(self):
        """base_path kwarg sets the base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            assert wl._default_session.token_path == Path(tmpdir) / "token.json"

    def test_send_auto_routes_to_correct_session(self):
        """send() should pick the session that has a context_token for the user."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(token_path=Path(tmpdir) / "token.json")

            # Default session has no context for the user
            wl._default_session.bot_info = BotInfo(
                bot_id="bot1@im.bot",
                base_url="https://example.com",
                token="tok1",
            )

            from weilink.client import _Session

            s2 = _Session(
                name="s2",
                token_path=Path(tmpdir) / "s2" / "token.json",
                bot_info=BotInfo(
                    bot_id="bot2@im.bot",
                    base_url="https://example.com",
                    token="tok2",
                ),
            )
            s2.context_tokens["user_s2@im.wechat"] = "ctx_s2"
            s2.context_timestamps["user_s2@im.wechat"] = time.time()
            wl._sessions["s2"] = s2

            # Sending to user_s2 without context in default → should return False
            # because no session has context for "unknown@im.wechat"
            result = wl.send("unknown@im.wechat", "hello")
            assert not result

    def test_rename_session(self):
        """rename_session() moves files and updates internal state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            wl._default_session.bot_info = BotInfo(
                bot_id="bot1@im.bot",
                base_url="https://example.com",
                token="tok1",
            )
            wl._default_session.context_tokens["user@im.wechat"] = "ctx"
            wl._default_session.context_timestamps["user@im.wechat"] = time.time()
            wl._save_state()
            wl._save_contexts()

            # Rename default -> pipi
            wl.rename_session("default", "pipi")

            assert "default" not in wl._sessions
            assert "pipi" in wl._sessions
            assert wl._default_session.name == "pipi"
            assert wl.bot_id == "bot1@im.bot"  # still accessible via default ref

            # Files moved
            assert (Path(tmpdir) / "pipi" / "token.json").exists()
            assert (Path(tmpdir) / "pipi" / "contexts.json").exists()
            # Old files cleaned up
            assert not (Path(tmpdir) / "token.json").exists()

    def test_rename_session_errors(self):
        """rename_session() raises on invalid names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            try:
                wl.rename_session("nonexistent", "new")
                assert False, "Should raise ValueError"
            except ValueError:
                pass

            # Duplicate name
            from weilink.client import _Session

            s2 = _Session(
                name="taken",
                token_path=Path(tmpdir) / "taken" / "token.json",
            )
            wl._sessions["taken"] = s2
            try:
                wl.rename_session("default", "taken")
                assert False, "Should raise ValueError"
            except ValueError:
                pass

    def test_logout_removes_files(self):
        """logout() deletes persisted files and removes the session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)

            # Create and save a named session
            session = wl._create_session("foo", Path(tmpdir) / "foo" / "token.json")
            session.bot_info = BotInfo(
                bot_id="bot_foo@im.bot",
                base_url="https://example.com",
                token="tok_foo",
            )
            wl._save_session_state(session)
            wl._save_session_contexts(session)
            assert (Path(tmpdir) / "foo" / "token.json").exists()

            wl.logout("foo")
            assert "foo" not in wl._sessions
            assert not (Path(tmpdir) / "foo" / "token.json").exists()
            assert not (Path(tmpdir) / "foo").exists()  # dir removed

    def test_logout_nonexistent_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            try:
                wl.logout("nonexistent")
                assert False, "Should raise ValueError"
            except ValueError:
                pass

    def test_auto_discover_sessions(self):
        """Named sessions on disk are auto-discovered on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-create session dirs with token files
            for name, bot_id in [("alice", "alice@im.bot"), ("bob", "bob@im.bot")]:
                d = Path(tmpdir) / name
                d.mkdir()
                (d / "token.json").write_text(
                    json.dumps(
                        {
                            "bot_id": bot_id,
                            "base_url": "https://example.com",
                            "token": f"tok_{name}",
                        }
                    )
                )

            wl = WeiLink(base_path=tmpdir)
            assert "alice" in wl.sessions
            assert "bob" in wl.sessions
            # No default token.json → phantom default is skipped
            assert "default" not in wl.sessions
            assert wl.bot_ids["alice"] == "alice@im.bot"
            assert wl.bot_ids["bob"] == "bob@im.bot"

    def test_auto_discover_ignores_non_session_dirs(self):
        """Directories without token.json are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "random_dir").mkdir()
            (Path(tmpdir) / "some_file.txt").write_text("not a session")

            wl = WeiLink(base_path=tmpdir)
            assert list(wl.sessions) == ["default"]


class TestSessionObject:
    """Tests for the public Session object."""

    def test_session_object_properties(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            token_path.write_text(
                json.dumps(
                    {
                        "bot_id": "bot1@im.bot",
                        "base_url": "https://example.com",
                        "token": "tok1",
                        "created_at": 1700000000.0,
                    }
                )
            )
            wl = WeiLink(token_path=token_path)
            s = wl.sessions["default"]
            assert s.name == "default"
            assert s.bot_id == "bot1@im.bot"
            assert s.is_connected is True
            assert s.is_default is True
            assert s.created_at == 1700000000.0

    def test_session_repr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            token_path.write_text(
                json.dumps(
                    {
                        "bot_id": "bot1@im.bot",
                        "base_url": "https://example.com",
                        "token": "tok1",
                    }
                )
            )
            wl = WeiLink(token_path=token_path)
            s = wl.sessions["default"]
            assert "connected" in repr(s)
            assert "default" in repr(s)

    def test_session_rename_via_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            wl._default_session.bot_info = BotInfo(
                bot_id="bot1@im.bot",
                base_url="https://example.com",
                token="tok1",
            )
            wl._save_state()

            wl.sessions["default"].rename("pipi")
            assert "default" not in wl.sessions
            assert "pipi" in wl.sessions

    def test_session_set_default_via_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            wl._default_session.bot_info = BotInfo(
                bot_id="bot1@im.bot",
                base_url="https://example.com",
                token="tok1",
            )

            from weilink.client import _Session

            s2 = _Session(
                name="zb",
                token_path=Path(tmpdir) / "zb" / "token.json",
                bot_info=BotInfo(
                    bot_id="bot2@im.bot",
                    base_url="https://example.com",
                    token="tok2",
                ),
            )
            wl._sessions["zb"] = s2

            assert wl.bot_id == "bot1@im.bot"
            wl.sessions["zb"].set_default()
            assert wl.bot_id == "bot2@im.bot"

    def test_session_logout_via_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            session = wl._create_session("foo", Path(tmpdir) / "foo" / "token.json")
            session.bot_info = BotInfo(
                bot_id="bot_foo@im.bot",
                base_url="https://example.com",
                token="tok_foo",
            )
            wl._save_session_state(session)

            wl.sessions["foo"].logout()
            assert "foo" not in wl.sessions

    def test_sessions_dict_iteration(self):
        """Iterating sessions gives session names (strings)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            names = list(wl.sessions)
            assert names == ["default"]
            assert all(isinstance(n, str) for n in names)

    def test_sessions_dict_access(self):
        """Dict-like access returns Session objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            s = wl.sessions["default"]
            from weilink.client import Session

            assert isinstance(s, Session)


class TestSetDefault:
    """Tests for set_default functionality."""

    def test_set_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)

            from weilink.client import _Session

            s2 = _Session(
                name="zb",
                token_path=Path(tmpdir) / "zb" / "token.json",
                bot_info=BotInfo(
                    bot_id="bot_zb@im.bot",
                    base_url="https://example.com",
                    token="tok_zb",
                ),
            )
            wl._sessions["zb"] = s2

            wl.set_default("zb")
            assert wl.bot_id == "bot_zb@im.bot"
            assert wl.sessions["zb"].is_default is True
            assert wl.sessions["default"].is_default is False

    def test_set_default_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            try:
                wl.set_default("nope")
                assert False, "Should raise ValueError"
            except ValueError:
                pass


class TestNameProtection:
    """Tests for 'default' name protection."""

    def test_login_name_default_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            try:
                wl.login(name="default")
                assert False, "Should raise ValueError"
            except ValueError as e:
                assert "reserved" in str(e)

    def test_rename_to_default_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            wl._default_session.bot_info = BotInfo(
                bot_id="bot1@im.bot",
                base_url="https://example.com",
                token="tok1",
            )

            from weilink.client import _Session

            s2 = _Session(
                name="foo",
                token_path=Path(tmpdir) / "foo" / "token.json",
            )
            wl._sessions["foo"] = s2
            try:
                wl.rename_session("foo", "default")
                assert False, "Should raise ValueError"
            except ValueError as e:
                assert "default" in str(e)


class TestSkipPhantomDefault:
    """Tests for skipping phantom default session."""

    def test_skip_phantom_default(self):
        """No default token + named sessions → no 'default' in sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a named session on disk (no default token.json)
            d = Path(tmpdir) / "zb"
            d.mkdir()
            (d / "token.json").write_text(
                json.dumps(
                    {
                        "bot_id": "zb@im.bot",
                        "base_url": "https://example.com",
                        "token": "tok_zb",
                        "created_at": 1700000000.0,
                    }
                )
            )

            wl = WeiLink(base_path=tmpdir)
            assert "default" not in wl.sessions
            assert "zb" in wl.sessions
            assert wl.bot_id == "zb@im.bot"

    def test_skip_phantom_default_picks_earliest(self):
        """With multiple named sessions, picks earliest created_at as default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for name, bot_id, ts in [
                ("beta", "beta@im.bot", 1700002000.0),
                ("alpha", "alpha@im.bot", 1700001000.0),
            ]:
                d = Path(tmpdir) / name
                d.mkdir()
                (d / "token.json").write_text(
                    json.dumps(
                        {
                            "bot_id": bot_id,
                            "base_url": "https://example.com",
                            "token": f"tok_{name}",
                            "created_at": ts,
                        }
                    )
                )

            wl = WeiLink(base_path=tmpdir)
            assert "default" not in wl.sessions
            # alpha has earlier created_at
            assert wl.bot_id == "alpha@im.bot"

    def test_first_use_creates_default(self):
        """No sessions at all → creates default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl = WeiLink(base_path=tmpdir)
            assert "default" in wl.sessions
            assert not wl.is_connected

    def test_default_token_exists_creates_default(self):
        """When default token.json exists, always creates default session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "token.json").write_text(
                json.dumps(
                    {
                        "bot_id": "default@im.bot",
                        "base_url": "https://example.com",
                        "token": "tok_default",
                    }
                )
            )
            # Also a named session
            d = Path(tmpdir) / "zb"
            d.mkdir()
            (d / "token.json").write_text(
                json.dumps(
                    {
                        "bot_id": "zb@im.bot",
                        "base_url": "https://example.com",
                        "token": "tok_zb",
                    }
                )
            )

            wl = WeiLink(base_path=tmpdir)
            assert "default" in wl.sessions
            assert "zb" in wl.sessions


class TestCreatedAt:
    """Tests for created_at persistence."""

    def test_created_at_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            wl = WeiLink(token_path=token_path)
            wl._bot_info = BotInfo(
                bot_id="test@im.bot",
                base_url="https://example.com",
                token="tok123",
            )
            wl._save_state()

            data = json.loads(token_path.read_text())
            assert "created_at" in data
            assert isinstance(data["created_at"], float)

            # Reload
            wl2 = WeiLink(token_path=token_path)
            assert wl2.sessions["default"].created_at == data["created_at"]

    def test_created_at_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            wl = WeiLink(token_path=token_path)
            wl._bot_info = BotInfo(
                bot_id="test@im.bot",
                base_url="https://example.com",
                token="tok123",
            )
            wl._save_state()

            first_ts = json.loads(token_path.read_text())["created_at"]

            # Save again — should keep original
            wl._save_state()
            second_ts = json.loads(token_path.read_text())["created_at"]
            assert first_ts == second_ts
