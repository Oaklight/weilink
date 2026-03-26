"""WeiLink - Lightweight Python SDK for WeChat iLink Bot protocol."""

__version__ = "0.4.0"

from weilink._protocol import (
    ILinkError,
    QuotaExhaustedError,
    SessionExpiredError,
    TextTooLongError,
)
from weilink.client import Session, WeiLink
from weilink.models import (
    BotInfo,
    FileInfo,
    ImageInfo,
    MediaContent,
    MediaInfo,
    Message,
    MessageType,
    RefMessage,
    SendResult,
    UploadedMedia,
    VideoInfo,
    VoiceInfo,
)

__all__ = [
    "ILinkError",
    "QuotaExhaustedError",
    "Session",
    "SessionExpiredError",
    "TextTooLongError",
    "WeiLink",
    "BotInfo",
    "FileInfo",
    "ImageInfo",
    "MediaContent",
    "MediaInfo",
    "Message",
    "MessageType",
    "RefMessage",
    "SendResult",
    "UploadedMedia",
    "VideoInfo",
    "VoiceInfo",
]
