"""Data models for iLink Bot protocol messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Union


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


class UploadMediaType(IntEnum):
    """Media type codes used in the getuploadurl endpoint."""

    IMAGE = 1
    VIDEO = 2
    FILE = 3
    VOICE = 4


class SendMediaType(IntEnum):
    """Media type codes used in the send message item_list."""

    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5


@dataclass(frozen=True)
class UploadedMedia:
    """Result of a CDN media pre-upload via ``WeiLink.upload()``.

    Pass this object to ``WeiLink.send()`` instead of raw bytes to reuse
    a previously uploaded file without re-uploading.

    Attributes:
        media_type: The media type used for this upload.
        filekey: Random hex filekey used for this upload.
        download_param: CDN download parameter (x-encrypted-param header).
        aes_key_hex: Hex-encoded AES key used for encryption.
        file_size: Original plaintext file size.
        cipher_size: Encrypted file size.
        file_name: Original file name (for files only).
    """

    media_type: UploadMediaType
    filekey: str
    download_param: str
    aes_key_hex: str
    file_size: int
    cipher_size: int
    file_name: str = ""


#: Type alias for media content accepted by :meth:`WeiLink.send`.
#: Can be raw ``bytes``, a pre-uploaded :class:`UploadedMedia` reference,
#: or a list of either for batch sending.
MediaContent = Union[bytes, UploadedMedia, list[Union[bytes, UploadedMedia]]]


@dataclass(frozen=True)
class BotInfo:
    """Bot credentials obtained after QR code login.

    Attributes:
        bot_id: Bot identifier (xxx@im.bot).
        base_url: iLink API base URL.
        token: Bearer token for authentication.
        user_id: WeChat user ID that authorized the bot (xxx@im.wechat).
    """

    bot_id: str
    base_url: str
    token: str
    user_id: str = ""


@dataclass(frozen=True)
class MediaInfo:
    """CDN media reference for encrypted files.

    Attributes:
        encrypt_query_param: CDN download query parameter.
        aes_key: AES-128-ECB key (hex or base64 encoded).
        encrypt_type: Encryption type identifier (typically 1).
        full_url: Direct CDN URL (when provided by server, bypasses
            URL construction from encrypt_query_param).
    """

    encrypt_query_param: str = ""
    aes_key: str = ""
    encrypt_type: int = 0
    full_url: str = ""


@dataclass(frozen=True)
class ImageInfo:
    """Image metadata from a received message.

    Attributes:
        media: CDN media reference for the full-size image.
        url: Direct image URL (may be empty).
        thumb_width: Thumbnail width in pixels.
        thumb_height: Thumbnail height in pixels.
        mid_size: Medium-quality image size in bytes.
        thumb_size: Thumbnail image size in bytes.
        hd_size: HD image cipher size in bytes.
    """

    media: MediaInfo = field(default_factory=MediaInfo)
    url: str = ""
    thumb_width: int = 0
    thumb_height: int = 0
    mid_size: int = 0
    thumb_size: int = 0
    hd_size: int = 0


@dataclass(frozen=True)
class VoiceInfo:
    """Voice message metadata from a received message.

    Attributes:
        media: CDN media reference for the voice file.
        playtime: Duration in milliseconds.
        text: Voice-to-text transcription (may be empty).
        encode_type: Audio codec (1=pcm, 2=adpcm, 4=speex, 5=amr, 6=silk, 7=mp3).
        bits_per_sample: Bit depth.
        sample_rate: Sample rate in Hz.
    """

    media: MediaInfo = field(default_factory=MediaInfo)
    playtime: int = 0
    text: str = ""
    encode_type: int = 0
    bits_per_sample: int = 0
    sample_rate: int = 0


@dataclass(frozen=True)
class FileInfo:
    """File attachment metadata from a received message.

    Attributes:
        media: CDN media reference for the file.
        file_name: Original file name.
        file_size: File size as string.
        md5: File MD5 checksum.
    """

    media: MediaInfo = field(default_factory=MediaInfo)
    file_name: str = ""
    file_size: str = ""
    md5: str = ""


@dataclass(frozen=True)
class VideoInfo:
    """Video metadata from a received message.

    Attributes:
        media: CDN media reference for the video.
        play_length: Duration in seconds.
        video_md5: Video file MD5 checksum.
        thumb_width: Thumbnail width in pixels.
        thumb_height: Thumbnail height in pixels.
        thumb_media: CDN media reference for the video thumbnail.
        video_size: Video file size in bytes.
        thumb_size: Thumbnail image size in bytes.
    """

    media: MediaInfo = field(default_factory=MediaInfo)
    play_length: int = 0
    video_md5: str = ""
    thumb_width: int = 0
    thumb_height: int = 0
    thumb_media: MediaInfo | None = None
    video_size: int = 0
    thumb_size: int = 0


@dataclass(frozen=True)
class RefMessage:
    """A quoted / referenced message embedded in a received message.

    When a WeChat user replies to (quotes) a previous message, the quoted
    content is available here.  Only content fields are present — the
    protocol does not expose sender, timestamp, or message-id for the
    referenced message.

    Attributes:
        msg_type: Content type of the referenced message.
        text: Text content, if msg_type is TEXT.
        image: Image metadata, if msg_type is IMAGE.
        voice: Voice metadata, if msg_type is VOICE.
        file: File metadata, if msg_type is FILE.
        video: Video metadata, if msg_type is VIDEO.
    """

    msg_type: MessageType = MessageType.TEXT
    text: str | None = None
    image: ImageInfo | None = None
    voice: VoiceInfo | None = None
    file: FileInfo | None = None
    video: VideoInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-friendly dict."""
        result: dict[str, Any] = {"msg_type": self.msg_type.name}
        if self.text is not None:
            result["text"] = self.text
        if self.image is not None:
            result["image"] = {
                "url": self.image.url,
                "thumb_width": self.image.thumb_width,
                "thumb_height": self.image.thumb_height,
            }
        if self.voice is not None:
            result["voice"] = {
                "playtime": self.voice.playtime,
                "text": self.voice.text,
            }
        if self.file is not None:
            result["file"] = {
                "file_name": self.file.file_name,
                "file_size": self.file.file_size,
            }
        if self.video is not None:
            result["video"] = {
                "play_length": self.video.play_length,
                "thumb_width": self.video.thumb_width,
                "thumb_height": self.video.thumb_height,
            }
        return result


@dataclass(frozen=True)
class Message:
    """A received WeChat message.

    Attributes:
        from_user: Sender identifier (xxx@im.wechat).
        msg_type: Content type (TEXT, IMAGE, VOICE, FILE, VIDEO).
        text: Text content, if any.
        image: Image metadata, if msg_type is IMAGE.
        voice: Voice metadata, if msg_type is VOICE.
        file: File metadata, if msg_type is FILE.
        video: Video metadata, if msg_type is VIDEO.
        timestamp: Creation time in milliseconds.
        message_id: Unique message identifier.
        context_token: Opaque token required for replying (managed internally).
        ref_msg: Quoted/referenced message, if this is a reply.
    """

    from_user: str
    msg_type: MessageType = MessageType.TEXT
    text: str | None = None
    image: ImageInfo | None = None
    voice: VoiceInfo | None = None
    file: FileInfo | None = None
    video: VideoInfo | None = None
    timestamp: int = 0
    message_id: int | None = None
    context_token: str = ""
    bot_id: str | None = None
    ref_msg: RefMessage | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-friendly dict."""
        result: dict[str, Any] = {
            "message_id": self.message_id,
            "from_user": self.from_user,
            "msg_type": self.msg_type.name,
            "timestamp": self.timestamp,
            "bot_id": self.bot_id,
        }
        if self.text is not None:
            result["text"] = self.text
        if self.image is not None:
            result["image"] = {
                "url": self.image.url,
                "thumb_width": self.image.thumb_width,
                "thumb_height": self.image.thumb_height,
            }
        if self.voice is not None:
            result["voice"] = {
                "playtime": self.voice.playtime,
                "text": self.voice.text,
            }
        if self.file is not None:
            result["file"] = {
                "file_name": self.file.file_name,
                "file_size": self.file.file_size,
            }
        if self.video is not None:
            result["video"] = {
                "play_length": self.video.play_length,
                "thumb_width": self.video.thumb_width,
                "thumb_height": self.video.thumb_height,
            }
        if self.ref_msg is not None:
            result["ref_msg"] = self.ref_msg.to_dict()
        return result


@dataclass
class SendResult:
    """Result of a ``WeiLink.send()`` call.

    Evaluates to ``True`` / ``False`` based on :attr:`success`, so
    ``if wl.send(...)`` continues to work as before.

    Attributes:
        success: Whether all sends succeeded.
        messages: Messages received during auto-recv (empty when
            ``auto_recv=False``).
        remaining: Number of outbound messages still available on the
            current context_token (out of 10).  ``None`` if unknown.
    """

    success: bool
    messages: list[Message] = field(default_factory=list)
    remaining: int | None = None

    def __bool__(self) -> bool:
        return self.success


@dataclass
class _UpdatesResponse:
    """Internal model for getupdates API response."""

    ret: int = 0
    errcode: int | None = None
    errmsg: str | None = None
    msgs: list[dict] = field(default_factory=list)
    get_updates_buf: str = ""
    longpolling_timeout_ms: int | None = None
