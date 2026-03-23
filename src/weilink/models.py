"""Data models for iLink Bot protocol messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class MessageType(IntEnum):
    """iLink message content types."""

    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5


class MessageDirection(IntEnum):
    """Who sent the message."""

    USER = 1
    BOT = 2


class MessageState(IntEnum):
    """Message completion state."""

    NEW = 0
    GENERATING = 1
    FINISH = 2


@dataclass(frozen=True)
class BotInfo:
    """Bot credentials obtained after QR code login.

    Attributes:
        bot_id: Bot identifier (xxx@im.bot).
        base_url: iLink API base URL.
        token: Bearer token for authentication.
    """

    bot_id: str
    base_url: str
    token: str


@dataclass(frozen=True)
class Message:
    """A received WeChat message.

    Attributes:
        from_user: Sender identifier (xxx@im.wechat).
        text: Text content, if any.
        msg_type: Content type (TEXT, IMAGE, VOICE, FILE, VIDEO).
        timestamp: Creation time in milliseconds.
        message_id: Unique message identifier.
        context_token: Opaque token required for replying (managed internally).
    """

    from_user: str
    msg_type: MessageType = MessageType.TEXT
    text: str | None = None
    timestamp: int = 0
    message_id: int | None = None
    context_token: str = ""


@dataclass
class _UpdatesResponse:
    """Internal model for getupdates API response."""

    ret: int = 0
    errcode: int | None = None
    errmsg: str | None = None
    msgs: list[dict] = field(default_factory=list)
    get_updates_buf: str = ""
    longpolling_timeout_ms: int | None = None
