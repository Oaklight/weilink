"""WeiLink - Lightweight Python SDK for WeChat iLink Bot protocol."""

__version__ = "0.3.0b2"

from weilink.client import WeiLink
from weilink.models import (
    BotInfo,
    FileInfo,
    ImageInfo,
    MediaContent,
    MediaInfo,
    Message,
    MessageType,
    UploadedMedia,
    VideoInfo,
    VoiceInfo,
)

__all__ = [
    "WeiLink",
    "BotInfo",
    "FileInfo",
    "ImageInfo",
    "MediaContent",
    "MediaInfo",
    "Message",
    "MessageType",
    "UploadedMedia",
    "VideoInfo",
    "VoiceInfo",
]
