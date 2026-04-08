"""Tests for weilink._store — SQLite message persistence."""

from __future__ import annotations

import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest

from weilink._store import (
    MessageStore,
    deserialize_message,
    serialize_message,
)
from weilink.models import (
    FileInfo,
    ImageInfo,
    MediaInfo,
    Message,
    MessageType,
    RefMessage,
    VideoInfo,
    VoiceInfo,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_messages.db"


@pytest.fixture
def store(db_path: Path) -> Generator[MessageStore]:
    s = MessageStore(db_path, max_age_days=None, max_count=None)
    yield s
    s.close()


def _make_text_msg(
    text: str = "hello",
    from_user: str = "user1@im.wechat",
    bot_id: str = "bot1@im.bot",
    message_id: int | None = 100,
    timestamp: int = 1700000000000,
) -> Message:
    return Message(
        from_user=from_user,
        msg_type=MessageType.TEXT,
        text=text,
        timestamp=timestamp,
        message_id=message_id,
        bot_id=bot_id,
    )


def _make_image_msg(message_id: int = 200) -> Message:
    return Message(
        from_user="user2@im.wechat",
        msg_type=MessageType.IMAGE,
        image=ImageInfo(
            media=MediaInfo(
                encrypt_query_param="param=abc",
                aes_key="deadbeef",
                encrypt_type=1,
                full_url="https://novac2c.cdn.weixin.qq.com/c2c/download?param=abc&taskid=t1",
            ),
            url="https://cdn.example.com/img.jpg",
            thumb_width=100,
            thumb_height=200,
            hd_size=5000,
        ),
        timestamp=1700000001000,
        message_id=message_id,
        bot_id="bot1@im.bot",
    )


def _make_voice_msg(message_id: int = 300) -> Message:
    return Message(
        from_user="user1@im.wechat",
        msg_type=MessageType.VOICE,
        voice=VoiceInfo(
            media=MediaInfo(aes_key="voicekey", encrypt_type=1),
            playtime=3000,
            text="transcribed text",
            encode_type=6,
            bits_per_sample=16,
            sample_rate=16000,
        ),
        timestamp=1700000002000,
        message_id=message_id,
        bot_id="bot1@im.bot",
    )


def _make_file_msg(message_id: int = 400) -> Message:
    return Message(
        from_user="user1@im.wechat",
        msg_type=MessageType.FILE,
        file=FileInfo(
            media=MediaInfo(aes_key="filekey"),
            file_name="doc.pdf",
            file_size="12345",
            md5="abc123",
        ),
        timestamp=1700000003000,
        message_id=message_id,
        bot_id="bot1@im.bot",
    )


def _make_video_msg(message_id: int = 500) -> Message:
    return Message(
        from_user="user2@im.wechat",
        msg_type=MessageType.VIDEO,
        video=VideoInfo(
            media=MediaInfo(aes_key="videokey"),
            play_length=60,
            video_md5="vid123",
            thumb_width=640,
            thumb_height=480,
        ),
        timestamp=1700000004000,
        message_id=message_id,
        bot_id="bot1@im.bot",
    )


def _make_ref_msg(message_id: int = 600) -> Message:
    return Message(
        from_user="user1@im.wechat",
        msg_type=MessageType.TEXT,
        text="reply",
        timestamp=1700000005000,
        message_id=message_id,
        bot_id="bot1@im.bot",
        ref_msg=RefMessage(
            msg_type=MessageType.TEXT,
            text="original message",
        ),
    )


# ------------------------------------------------------------------
# Serialization round-trip tests
# ------------------------------------------------------------------


class TestSerialization:
    def test_text_roundtrip(self):
        msg = _make_text_msg()
        restored = deserialize_message(serialize_message(msg))
        assert restored.from_user == msg.from_user
        assert restored.msg_type == msg.msg_type
        assert restored.text == msg.text
        assert restored.timestamp == msg.timestamp
        assert restored.message_id == msg.message_id
        assert restored.bot_id == msg.bot_id

    def test_image_roundtrip(self):
        msg = _make_image_msg()
        restored = deserialize_message(serialize_message(msg))
        assert restored.image is not None
        assert msg.image is not None
        assert restored.image.url == msg.image.url
        assert restored.image.media.aes_key == msg.image.media.aes_key
        assert (
            restored.image.media.encrypt_query_param
            == msg.image.media.encrypt_query_param
        )
        assert restored.image.hd_size == msg.image.hd_size

    def test_voice_roundtrip(self):
        msg = _make_voice_msg()
        restored = deserialize_message(serialize_message(msg))
        assert restored.voice is not None
        assert msg.voice is not None
        assert restored.voice.playtime == msg.voice.playtime
        assert restored.voice.text == msg.voice.text
        assert restored.voice.encode_type == 6
        assert restored.voice.sample_rate == 16000

    def test_file_roundtrip(self):
        msg = _make_file_msg()
        restored = deserialize_message(serialize_message(msg))
        assert restored.file is not None
        assert restored.file.file_name == "doc.pdf"
        assert restored.file.md5 == "abc123"

    def test_video_roundtrip(self):
        msg = _make_video_msg()
        restored = deserialize_message(serialize_message(msg))
        assert restored.video is not None
        assert restored.video.play_length == 60
        assert restored.video.thumb_width == 640

    def test_ref_msg_roundtrip(self):
        msg = _make_ref_msg()
        restored = deserialize_message(serialize_message(msg))
        assert restored.ref_msg is not None
        assert restored.ref_msg.text == "original message"
        assert restored.ref_msg.msg_type == MessageType.TEXT


# ------------------------------------------------------------------
# Store CRUD tests
# ------------------------------------------------------------------


class TestMessageStore:
    def test_store_and_get_by_id(self, store: MessageStore):
        msg = _make_text_msg(message_id=42)
        store.store([msg])
        result = store.get_by_id(42)
        assert result is not None
        assert result.text == "hello"
        assert result.message_id == 42

    def test_get_by_id_missing(self, store: MessageStore):
        assert store.get_by_id(999) is None

    def test_deduplication(self, store: MessageStore):
        msg = _make_text_msg(message_id=42)
        store.store([msg])
        store.store([msg])  # same message_id
        assert store.count() == 1

    def test_store_multiple_types(self, store: MessageStore):
        msgs = [
            _make_text_msg(message_id=1),
            _make_image_msg(message_id=2),
            _make_voice_msg(message_id=3),
            _make_file_msg(message_id=4),
            _make_video_msg(message_id=5),
        ]
        store.store(msgs)
        assert store.count() == 5

        # Verify media info preserved via get_by_id
        img = store.get_by_id(2)
        assert img is not None
        assert img.image is not None
        assert img.image.media.aes_key == "deadbeef"

    def test_store_sent(self, store: MessageStore):
        store.store_sent(user_id="user1@im.wechat", bot_id="bot1@im.bot", text="hi")
        results = store.query(direction=2)
        assert len(results) == 1
        assert results[0]["text"] == "hi"
        assert results[0]["direction"] == "sent"

    def test_query_by_user(self, store: MessageStore):
        store.store(
            [
                _make_text_msg(from_user="alice@im.wechat", message_id=1),
                _make_text_msg(from_user="bob@im.wechat", message_id=2),
                _make_text_msg(from_user="alice@im.wechat", message_id=3),
            ]
        )
        results = store.query(user_id="alice@im.wechat")
        assert len(results) == 2

    def test_query_by_msg_type(self, store: MessageStore):
        store.store([_make_text_msg(message_id=1), _make_image_msg(message_id=2)])
        results = store.query(msg_type=MessageType.IMAGE.value)
        assert len(results) == 1
        assert results[0]["msg_type"] == "IMAGE"

    def test_query_time_range(self, store: MessageStore):
        store.store(
            [
                _make_text_msg(message_id=1, timestamp=1000),
                _make_text_msg(message_id=2, timestamp=2000),
                _make_text_msg(message_id=3, timestamp=3000),
            ]
        )
        results = store.query(since_ms=1500, until_ms=2500)
        assert len(results) == 1

    def test_query_text_contains(self, store: MessageStore):
        store.store(
            [
                _make_text_msg(text="hello world", message_id=1),
                _make_text_msg(text="goodbye", message_id=2),
            ]
        )
        results = store.query(text_contains="hello")
        assert len(results) == 1
        assert results[0]["text"] == "hello world"

    def test_query_limit_offset(self, store: MessageStore):
        msgs = [_make_text_msg(message_id=i, timestamp=i * 1000) for i in range(10)]
        store.store(msgs)
        page1 = store.query(limit=3, offset=0)
        page2 = store.query(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0]["message_id"] != page2[0]["message_id"]

    def test_count(self, store: MessageStore):
        store.store([_make_text_msg(message_id=i) for i in range(5)])
        assert store.count() == 5
        assert store.count(user_id="user1@im.wechat") == 5
        assert store.count(user_id="nobody@im.wechat") == 0


# ------------------------------------------------------------------
# Pruning tests
# ------------------------------------------------------------------


class TestPruning:
    def test_prune_by_count(self, db_path: Path):
        store = MessageStore(db_path, max_age_days=None, max_count=3)
        msgs = [_make_text_msg(message_id=i, timestamp=i * 1000) for i in range(5)]
        store.store(msgs)
        store.prune()
        assert store.count() == 3
        store.close()

    def test_prune_by_age(self, db_path: Path):
        store = MessageStore(db_path, max_age_days=0, max_count=None)
        store.store([_make_text_msg(message_id=1)])
        # stored_at is "now", max_age_days=0 means cutoff=now
        time.sleep(0.1)
        deleted = store.prune()
        assert deleted >= 1
        store.close()


# ------------------------------------------------------------------
# Thread safety test
# ------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_writes(self, store: MessageStore):
        errors: list[Exception] = []

        def writer(start_id: int):
            try:
                for i in range(20):
                    store.store([_make_text_msg(message_id=start_id + i)])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i * 100,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert store.count() == 100


# ------------------------------------------------------------------
# Schema migration test
# ------------------------------------------------------------------


class TestMigration:
    def test_reopen_preserves_data(self, db_path: Path):
        store = MessageStore(db_path)
        store.store([_make_text_msg(message_id=42)])
        store.close()

        store2 = MessageStore(db_path)
        result = store2.get_by_id(42)
        assert result is not None
        assert result.text == "hello"
        store2.close()


# ------------------------------------------------------------------
# query_messages tests (Route C support)
# ------------------------------------------------------------------


class TestQueryMessages:
    def test_returns_message_objects(self, store: MessageStore):
        store.store([_make_text_msg(message_id=1)])
        results = store.query_messages()
        assert len(results) == 1
        assert isinstance(results[0], Message)
        assert results[0].text == "hello"

    def test_filter_by_bot_id(self, store: MessageStore):
        store.store(
            [
                _make_text_msg(message_id=1, bot_id="bot_a@im.bot"),
                _make_text_msg(message_id=2, bot_id="bot_b@im.bot"),
            ]
        )
        results = store.query_messages(bot_id="bot_a@im.bot")
        assert len(results) == 1
        assert results[0].bot_id == "bot_a@im.bot"

    def test_filter_by_direction(self, store: MessageStore):
        store.store([_make_text_msg(message_id=1)], direction=1)
        store.store([_make_text_msg(message_id=2)], direction=2)
        received = store.query_messages(direction=1)
        assert len(received) == 1
        assert received[0].message_id == 1

    def test_filter_by_since_ms(self, store: MessageStore):
        store.store(
            [
                _make_text_msg(message_id=1, timestamp=1000),
                _make_text_msg(message_id=2, timestamp=2000),
                _make_text_msg(message_id=3, timestamp=3000),
            ]
        )
        results = store.query_messages(since_ms=2000)
        assert len(results) == 2

    def test_preserves_media_info(self, store: MessageStore):
        store.store([_make_image_msg(message_id=10)])
        results = store.query_messages()
        assert len(results) == 1
        assert results[0].image is not None
        assert results[0].image.media.aes_key == "deadbeef"


# ------------------------------------------------------------------
# full_url persistence tests
# ------------------------------------------------------------------


class TestFullUrlPersistence:
    """Verify that MediaInfo.full_url survives serialization roundtrip."""

    def test_image_full_url_roundtrip(self):
        msg = _make_image_msg()
        restored = deserialize_message(serialize_message(msg))
        assert restored.image is not None
        assert msg.image is not None
        assert restored.image.media.full_url == msg.image.media.full_url
        assert "taskid=" in restored.image.media.full_url

    def test_voice_full_url_roundtrip(self):
        msg = Message(
            from_user="user1@im.wechat",
            msg_type=MessageType.VOICE,
            voice=VoiceInfo(
                media=MediaInfo(
                    aes_key="voicekey",
                    full_url="https://cdn.example.com/voice?taskid=v1",
                ),
                playtime=3000,
            ),
            timestamp=1700000002000,
            message_id=301,
            bot_id="bot1@im.bot",
        )
        restored = deserialize_message(serialize_message(msg))
        assert restored.voice is not None
        assert (
            restored.voice.media.full_url == "https://cdn.example.com/voice?taskid=v1"
        )

    def test_file_full_url_roundtrip(self):
        msg = Message(
            from_user="user1@im.wechat",
            msg_type=MessageType.FILE,
            file=FileInfo(
                media=MediaInfo(
                    aes_key="filekey",
                    full_url="https://cdn.example.com/file?taskid=f1",
                ),
                file_name="doc.pdf",
                file_size="12345",
            ),
            timestamp=1700000003000,
            message_id=401,
            bot_id="bot1@im.bot",
        )
        restored = deserialize_message(serialize_message(msg))
        assert restored.file is not None
        assert restored.file.media.full_url == "https://cdn.example.com/file?taskid=f1"

    def test_video_full_url_roundtrip(self):
        msg = Message(
            from_user="user2@im.wechat",
            msg_type=MessageType.VIDEO,
            video=VideoInfo(
                media=MediaInfo(
                    aes_key="videokey",
                    full_url="https://cdn.example.com/video?taskid=vid1",
                ),
                play_length=60,
            ),
            timestamp=1700000004000,
            message_id=501,
            bot_id="bot1@im.bot",
        )
        restored = deserialize_message(serialize_message(msg))
        assert restored.video is not None
        assert (
            restored.video.media.full_url == "https://cdn.example.com/video?taskid=vid1"
        )

    def test_store_roundtrip_preserves_full_url(self, store: MessageStore):
        msg = _make_image_msg(message_id=10)
        store.store([msg])
        result = store.get_by_id(10)
        assert result is not None
        assert result.image is not None
        assert result.image.media.full_url == msg.image.media.full_url

    def test_legacy_data_without_full_url(self):
        """Old stored messages lacking full_url should deserialize with empty string."""
        from weilink._store import _deserialize_media_info

        legacy = {"encrypt_query_param": "old_param", "aes_key": "old_key"}
        mi = _deserialize_media_info(legacy)
        assert mi.full_url == ""
        assert mi.encrypt_query_param == "old_param"
