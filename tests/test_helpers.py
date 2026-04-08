"""Tests for weilink._helpers module."""

from __future__ import annotations

import pytest

from weilink._helpers import (
    MEDIA_EXT_MAP,
    MEDIA_MIME_MAP,
    QRResult,
    media_filename,
    parse_direction,
    parse_message_type,
    parse_time,
    process_qr_status,
)
from weilink.models import BotInfo, FileInfo, Message, MessageType


# -- Constants ---------------------------------------------------------------


class TestMediaMaps:
    def test_ext_map_entries(self):
        assert MEDIA_EXT_MAP[MessageType.IMAGE] == ".jpg"
        assert MEDIA_EXT_MAP[MessageType.VOICE] == ".amr"
        assert MEDIA_EXT_MAP[MessageType.VIDEO] == ".mp4"

    def test_ext_map_excludes_text_and_file(self):
        assert MessageType.TEXT not in MEDIA_EXT_MAP
        assert MessageType.FILE not in MEDIA_EXT_MAP

    def test_mime_map_entries(self):
        assert MEDIA_MIME_MAP[MessageType.IMAGE] == "image/jpeg"
        assert MEDIA_MIME_MAP[MessageType.VOICE] == "audio/amr"
        assert MEDIA_MIME_MAP[MessageType.VIDEO] == "video/mp4"

    def test_mime_map_excludes_text_and_file(self):
        assert MessageType.TEXT not in MEDIA_MIME_MAP
        assert MessageType.FILE not in MEDIA_MIME_MAP


# -- media_filename ----------------------------------------------------------


class TestMediaFilename:
    def test_uses_file_name_when_present(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.FILE,
            file=FileInfo(file_name="report.pdf"),
            message_id=42,
        )
        assert media_filename(msg) == "report.pdf"

    def test_image_fallback(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.IMAGE,
            message_id=100,
        )
        assert media_filename(msg) == "100.jpg"

    def test_voice_fallback(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.VOICE,
            message_id=200,
        )
        assert media_filename(msg) == "200.amr"

    def test_video_fallback(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.VIDEO,
            message_id=300,
        )
        assert media_filename(msg) == "300.mp4"

    def test_text_fallback_to_bin(self):
        msg = Message(
            from_user="u@im.wechat",
            msg_type=MessageType.TEXT,
            message_id=400,
        )
        assert media_filename(msg) == "400.bin"


# -- parse_direction ---------------------------------------------------------


class TestParseDirection:
    def test_received(self):
        assert parse_direction("received") == 1

    def test_sent(self):
        assert parse_direction("sent") == 2

    def test_case_insensitive(self):
        assert parse_direction("RECEIVED") == 1
        assert parse_direction("Sent") == 2

    def test_invalid(self):
        assert parse_direction("invalid") is None

    def test_empty(self):
        assert parse_direction("") is None


# -- parse_message_type ------------------------------------------------------


class TestParseMessageType:
    def test_image(self):
        assert parse_message_type("IMAGE") == 2

    def test_case_insensitive(self):
        assert parse_message_type("image") == 2
        assert parse_message_type("Voice") == 3

    def test_all_types(self):
        assert parse_message_type("TEXT") == 1
        assert parse_message_type("FILE") == 4
        assert parse_message_type("VIDEO") == 5

    def test_invalid(self):
        assert parse_message_type("invalid") is None

    def test_empty(self):
        assert parse_message_type("") is None


# -- parse_time --------------------------------------------------------------


class TestParseTime:
    def test_unix_ms(self):
        assert parse_time("1234567890") == 1234567890

    def test_iso_utc(self):
        result = parse_time("2024-01-01T00:00:00Z")
        assert result == 1704067200000

    def test_iso_offset(self):
        result = parse_time("2024-01-01T08:00:00+08:00")
        assert result == 1704067200000

    def test_invalid(self):
        assert parse_time("not-a-time") is None

    def test_empty(self):
        assert parse_time("") is None


# -- process_qr_status ------------------------------------------------------


class TestProcessQrStatus:
    def test_confirmed(self):
        resp = {
            "status": "confirmed",
            "bot_token": "tok123",
            "baseurl": "https://example.com",
            "ilink_bot_id": "bot@im.bot",
            "ilink_user_id": "user@im.wechat",
        }
        qr = process_qr_status(resp)
        assert qr.status == "confirmed"
        assert isinstance(qr.bot_info, BotInfo)
        assert qr.bot_info.bot_id == "bot@im.bot"
        assert qr.bot_info.base_url == "https://example.com"
        assert qr.bot_info.token == "tok123"
        assert qr.bot_info.user_id == "user@im.wechat"

    def test_confirmed_missing_fields(self):
        resp = {"status": "confirmed"}
        qr = process_qr_status(resp)
        assert qr.status == "confirmed"
        assert qr.bot_info is not None
        assert qr.bot_info.bot_id == ""
        assert qr.bot_info.token == ""

    def test_scaned_normalized(self):
        resp = {"status": "scaned"}
        qr = process_qr_status(resp)
        assert qr.status == "scanned"
        assert qr.bot_info is None

    def test_expired(self):
        resp = {"status": "expired"}
        qr = process_qr_status(resp)
        assert qr.status == "expired"
        assert qr.bot_info is None

    def test_wait(self):
        resp = {"status": "wait"}
        qr = process_qr_status(resp)
        assert qr.status == "waiting"
        assert qr.bot_info is None

    def test_empty_status(self):
        resp = {"status": ""}
        qr = process_qr_status(resp)
        assert qr.status == "waiting"

    def test_missing_status(self):
        resp = {}
        qr = process_qr_status(resp)
        assert qr.status == "waiting"

    def test_unknown_status(self):
        resp = {"status": "something_new"}
        qr = process_qr_status(resp)
        assert qr.status == "waiting"

    def test_frozen(self):
        qr = QRResult(status="waiting")
        with pytest.raises(AttributeError):
            qr.status = "confirmed"
