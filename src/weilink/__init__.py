"""WeiLink - Lightweight Python SDK for WeChat iLink Bot protocol."""

__version__ = "0.3.0"

from weilink.client import Session, WeiLink
from weilink.models import (
    BotInfo,
    FileInfo,
    ImageInfo,
    MediaContent,
    MediaInfo,
    Message,
    MessageType,
    SendResult,
    UploadedMedia,
    VideoInfo,
    VoiceInfo,
)

__all__ = [
    "Session",
    "WeiLink",
    "BotInfo",
    "FileInfo",
    "ImageInfo",
    "MediaContent",
    "MediaInfo",
    "Message",
    "MessageType",
    "SendResult",
    "UploadedMedia",
    "VideoInfo",
    "VoiceInfo",
]
