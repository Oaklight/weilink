"""WeiLink client - public API for WeChat iLink Bot protocol."""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

from weilink import _protocol as proto
from weilink.models import (
    BotInfo,
    FileInfo,
    ImageInfo,
    MediaInfo,
    Message,
    MessageType,
    UploadMediaType,
    VideoInfo,
    VoiceInfo,
)

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_PATH = Path.home() / ".weilink" / "token.json"


class WeiLink:
    """Lightweight WeChat iLink Bot client.

    Provides register/send/recv message queue semantics over the iLink protocol.

    Example::

        wl = WeiLink()
        wl.login()

        # Receive messages
        messages = wl.recv()
        for msg in messages:
            print(f"{msg.from_user}: {msg.text}")

        # Reply
        wl.send(msg.from_user, "Got it!")

        wl.close()
    """

    def __init__(self, token_path: str | Path | None = None):
        """Initialize the WeiLink client.

        Args:
            token_path: Path to persist bot credentials.
                Defaults to ~/.weilink/token.json.
        """
        self._token_path = Path(token_path) if token_path else _DEFAULT_TOKEN_PATH
        self._bot_info: BotInfo | None = None
        self._cursor: str = ""
        self._context_tokens: dict[str, str] = {}
        self._context_timestamps: dict[str, float] = {}
        self._typing_tickets: dict[str, str] = {}
        self._load_state()
        self._load_contexts()

    def _load_state(self) -> None:
        """Load persisted bot credentials and cursor."""
        if not self._token_path.exists():
            return
        try:
            data = json.loads(self._token_path.read_text())
            self._bot_info = BotInfo(
                bot_id=data["bot_id"],
                base_url=data["base_url"],
                token=data["token"],
            )
            self._cursor = data.get("cursor", "")
            logger.info("Loaded credentials for %s", self._bot_info.bot_id)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load state from %s: %s", self._token_path, e)

    def _save_state(self) -> None:
        """Persist bot credentials and cursor to disk."""
        if not self._bot_info:
            return
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "bot_id": self._bot_info.bot_id,
            "base_url": self._bot_info.base_url,
            "token": self._bot_info.token,
            "cursor": self._cursor,
        }
        self._token_path.write_text(json.dumps(data, indent=2))

    @property
    def _contexts_path(self) -> Path:
        """Path to the contexts persistence file (sibling to token.json)."""
        return self._token_path.parent / "contexts.json"

    def _load_contexts(self) -> None:
        """Load persisted context tokens, discarding entries older than 24h.

        [Experimental] Context tokens are stored separately from bot
        credentials in ``contexts.json`` with per-entry timestamps so that
        stale entries can be auto-expired on load.
        """
        if not self._contexts_path.exists():
            return
        try:
            data = json.loads(self._contexts_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "Failed to load contexts from %s: %s", self._contexts_path, e
            )
            return

        now = time.time()
        expiry = 24 * 3600  # 24 hours in seconds
        for user_id, entry in data.items():
            if not isinstance(entry, dict):
                continue
            token = entry.get("t", "")
            ts = entry.get("ts", 0.0)
            if token and (now - ts) < expiry:
                self._context_tokens[user_id] = token
                self._context_timestamps[user_id] = ts

        logger.debug(
            "Loaded %d context token(s) from %s",
            len(self._context_tokens),
            self._contexts_path,
        )

    def _save_contexts(self) -> None:
        """Persist current context tokens to disk.

        [Experimental] Writes only when called explicitly (on context_token
        change), not on every ``_save_state()`` call.
        """
        self._contexts_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            user_id: {"t": token, "ts": self._context_timestamps.get(user_id, 0.0)}
            for user_id, token in self._context_tokens.items()
        }
        self._contexts_path.write_text(json.dumps(data, indent=2))

    @property
    def is_connected(self) -> bool:
        """Whether the client has valid credentials."""
        return self._bot_info is not None

    @property
    def bot_id(self) -> str | None:
        """Current bot identifier, or None if not logged in."""
        return self._bot_info.bot_id if self._bot_info else None

    def login(self, force: bool = False) -> BotInfo:
        """Login via QR code scan.

        If valid credentials exist on disk and force is False, reuses them.

        Args:
            force: Force a new QR code login even if credentials exist.

        Returns:
            BotInfo with bot_id, base_url, and token.
        """
        if self._bot_info and not force:
            logger.info(
                "Already logged in as %s (use force=True to re-login)",
                self._bot_info.bot_id,
            )
            return self._bot_info

        # Step 1: Get QR code
        qr_resp = proto.get_qr_code()
        qrcode = qr_resp["qrcode"]
        qr_url = qr_resp.get("qrcode_img_content", "")

        self._display_qr(qr_url)

        # Step 2: Poll for scan confirmation (5 min deadline)
        deadline = time.monotonic() + 300
        print("Waiting for scan...", end="", flush=True)
        while time.monotonic() < deadline:
            try:
                status_resp = proto.poll_qr_status(qrcode)
            except (proto.ILinkError, TimeoutError, OSError):
                # Long-poll timeout is normal, retry
                print(".", end="", flush=True)
                continue

            status = status_resp.get("status", "")

            if status == "confirmed":
                bot_token = status_resp.get("bot_token", "")
                base_url = status_resp.get("baseurl", proto.BASE_URL)
                bot_id = status_resp.get("ilink_bot_id", "")

                self._bot_info = BotInfo(
                    bot_id=bot_id,
                    base_url=base_url,
                    token=bot_token,
                )
                self._cursor = ""
                self._save_state()
                print(f"\nLogin successful! Bot ID: {bot_id}")
                return self._bot_info

            if status == "scaned":
                print("\nScanned, confirm on your phone...", end="", flush=True)
                continue

            if status == "expired":
                print("\nQR code expired, refreshing...")
                qr_resp = proto.get_qr_code()
                qrcode = qr_resp["qrcode"]
                qr_url = qr_resp.get("qrcode_img_content", "")
                self._display_qr(qr_url)
                print("Waiting for scan...", end="", flush=True)
                continue

            # status == "wait" or unknown
            print(".", end="", flush=True)

        raise proto.ILinkError(ret=-1, errmsg="QR code login timed out (5 min)")

    def recv(self, timeout: float = 35.0) -> list[Message]:
        """Receive pending messages via long-polling.

        Blocks for up to `timeout` seconds waiting for new messages.
        Automatically manages the sync cursor.

        Args:
            timeout: Maximum wait time in seconds.

        Returns:
            List of received messages (may be empty on timeout).

        Raises:
            RuntimeError: If not logged in.
            SessionExpiredError: If session has expired (re-login needed).
        """
        self._ensure_connected()
        assert self._bot_info is not None

        resp = proto.get_updates(
            cursor=self._cursor,
            token=self._bot_info.token,
            base_url=self._bot_info.base_url,
        )

        # Update cursor
        new_cursor = resp.get("get_updates_buf", "")
        if new_cursor:
            self._cursor = new_cursor
            self._save_state()

        # Parse messages
        context_changed = False
        messages: list[Message] = []
        for raw_msg in resp.get("msgs", []):
            # Only process user messages (message_type=1)
            if raw_msg.get("message_type") != 1:
                continue

            msg = self._parse_message(raw_msg)
            if msg:
                # Cache context_token for this user
                if msg.context_token:
                    self._context_tokens[msg.from_user] = msg.context_token
                    self._context_timestamps[msg.from_user] = time.time()
                    context_changed = True
                messages.append(msg)

        if context_changed:
            self._save_contexts()

        return messages

    def send(self, to: str, text: str) -> bool:
        """Send a text message to a user.

        Uses the cached context_token from the most recent message received
        from this user. Returns False if no context_token is available.

        Args:
            to: Target user ID (xxx@im.wechat).
            text: Message text.

        Returns:
            True if sent successfully, False if no valid context_token.

        Raises:
            RuntimeError: If not logged in.
        """
        self._ensure_connected()
        assert self._bot_info is not None

        ctx_token = self._context_tokens.get(to)
        if not ctx_token:
            logger.warning("No context_token for user %s, cannot send", to)
            return False

        try:
            resp = proto.send_message(
                to_user=to,
                text=text,
                context_token=ctx_token,
                token=self._bot_info.token,
                base_url=self._bot_info.base_url,
            )
            ret = resp.get("ret", 0)
            if ret != 0:
                logger.warning(
                    "send to %s returned ret=%s: %s", to, ret, resp.get("errmsg", "")
                )
                return False
            return True
        except proto.ILinkError as e:
            logger.error("Failed to send message to %s: %s", to, e)
            return False

    def send_typing(self, to: str) -> None:
        """Show "typing" indicator to a user.

        Args:
            to: Target user ID.
        """
        self._set_typing(to, status=1)

    def stop_typing(self, to: str) -> None:
        """Cancel "typing" indicator for a user.

        Args:
            to: Target user ID.
        """
        self._set_typing(to, status=2)

    def download(self, msg: Message) -> bytes:
        """Download media from a received message.

        Supports IMAGE, VOICE, FILE, and VIDEO message types.
        Requires ``weilink[media]`` (pycryptodome).

        Args:
            msg: A received Message with media content.

        Returns:
            Decrypted file bytes.

        Raises:
            ImportError: If pycryptodome is not installed.
            ValueError: If the message has no downloadable media.
        """
        from weilink._cdn import download_media

        media = self._get_media_info(msg)
        if not media or not media.encrypt_query_param:
            raise ValueError(
                f"Message has no downloadable media (type={msg.msg_type.name})"
            )

        return download_media(media.encrypt_query_param, media.aes_key)

    def send_image(self, to: str, image_data: bytes) -> bool:
        """Send an image to a user.

        Requires ``weilink[media]`` (pycryptodome).

        Args:
            to: Target user ID (xxx@im.wechat).
            image_data: Raw image bytes (JPEG, PNG, etc.).

        Returns:
            True if sent successfully.

        Raises:
            ImportError: If pycryptodome is not installed.
            RuntimeError: If not logged in.
        """
        return self._send_media(to, image_data, UploadMediaType.IMAGE, "image_item")

    def send_voice(self, to: str, voice_data: bytes) -> bool:
        """Send a voice message to a user.

        Requires ``weilink[media]`` (pycryptodome).

        Args:
            to: Target user ID (xxx@im.wechat).
            voice_data: Raw voice file bytes.

        Returns:
            True if sent successfully.

        Raises:
            ImportError: If pycryptodome is not installed.
            RuntimeError: If not logged in.
        """
        return self._send_media(to, voice_data, UploadMediaType.VOICE, "voice_item")

    def send_file(self, to: str, file_data: bytes, file_name: str) -> bool:
        """Send a file to a user.

        Requires ``weilink[media]`` (pycryptodome).

        Args:
            to: Target user ID (xxx@im.wechat).
            file_data: Raw file bytes.
            file_name: Original file name.

        Returns:
            True if sent successfully.

        Raises:
            ImportError: If pycryptodome is not installed.
            RuntimeError: If not logged in.
        """
        return self._send_media(
            to, file_data, UploadMediaType.FILE, "file_item", file_name=file_name
        )

    def send_video(self, to: str, video_data: bytes) -> bool:
        """Send a video to a user.

        Requires ``weilink[media]`` (pycryptodome).

        Args:
            to: Target user ID (xxx@im.wechat).
            video_data: Raw video file bytes.

        Returns:
            True if sent successfully.

        Raises:
            ImportError: If pycryptodome is not installed.
            RuntimeError: If not logged in.
        """
        return self._send_media(to, video_data, UploadMediaType.VIDEO, "video_item")

    def close(self) -> None:
        """Save state and clean up."""
        self._save_state()

    def __enter__(self) -> WeiLink:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @staticmethod
    def _display_qr(url: str) -> None:
        """Display QR code in terminal, with fallback to URL."""
        if not url:
            print("\n(No QR code URL received from server)\n")
            return

        print(f"\nScan this QR code with WeChat:\n{url}\n")

        from weilink._qr import print_qr_terminal

        print_qr_terminal(url)

    def _ensure_connected(self) -> None:
        """Raise if not logged in."""
        if not self._bot_info:
            raise RuntimeError("Not logged in. Call login() first.")

    def _parse_message(self, raw: dict[str, Any]) -> Message | None:
        """Parse a raw iLink message dict into a Message."""
        from_user = raw.get("from_user_id", "")
        if not from_user:
            return None

        # Extract content from item_list
        text: str | None = None
        image: ImageInfo | None = None
        voice: VoiceInfo | None = None
        file: FileInfo | None = None
        video: VideoInfo | None = None
        msg_type = MessageType.TEXT

        items = raw.get("item_list", [])
        if items:
            first = items[0]
            item_type = first.get("type", 1)
            msg_type = (
                MessageType(item_type)
                if item_type in MessageType.__members__.values()
                else MessageType.TEXT
            )

            if item_type == 1 and first.get("text_item"):
                text = first["text_item"].get("text")
            elif item_type == 2 and first.get("image_item"):
                image = self._parse_image_item(first["image_item"])
            elif item_type == 3 and first.get("voice_item"):
                voice = self._parse_voice_item(first["voice_item"])
            elif item_type == 4 and first.get("file_item"):
                file = self._parse_file_item(first["file_item"])
            elif item_type == 5 and first.get("video_item"):
                video = self._parse_video_item(first["video_item"])

        return Message(
            from_user=from_user,
            text=text,
            msg_type=msg_type,
            image=image,
            voice=voice,
            file=file,
            video=video,
            timestamp=raw.get("create_time_ms", 0),
            message_id=raw.get("message_id"),
            context_token=raw.get("context_token", ""),
        )

    @staticmethod
    def _parse_media_info(raw: dict[str, Any]) -> MediaInfo:
        """Parse a CDN media reference from a raw dict."""
        return MediaInfo(
            encrypt_query_param=raw.get("encrypt_query_param", ""),
            aes_key=raw.get("aes_key", ""),
            encrypt_type=raw.get("encrypt_type", 0),
        )

    @classmethod
    def _parse_image_item(cls, raw: dict[str, Any]) -> ImageInfo:
        """Parse an image_item dict into ImageInfo.

        ImageItem has a top-level ``aeskey`` field (raw hex string) that is
        preferred over ``media.aes_key`` (base64-encoded) for decryption,
        matching the official TypeScript SDK behaviour.
        """
        media = cls._parse_media_info(raw.get("media", {}))
        # Prefer image_item.aeskey (raw hex) over media.aes_key (base64)
        raw_aeskey_hex = raw.get("aeskey", "")
        if raw_aeskey_hex:
            media = MediaInfo(
                encrypt_query_param=media.encrypt_query_param,
                aes_key=raw_aeskey_hex,
                encrypt_type=media.encrypt_type,
            )
        return ImageInfo(
            media=media,
            url=raw.get("url", ""),
            thumb_width=raw.get("thumb_width", 0),
            thumb_height=raw.get("thumb_height", 0),
        )

    @classmethod
    def _parse_voice_item(cls, raw: dict[str, Any]) -> VoiceInfo:
        """Parse a voice_item dict into VoiceInfo."""
        media = cls._parse_media_info(raw.get("media", {}))
        return VoiceInfo(
            media=media,
            playtime=raw.get("playtime", 0),
            text=raw.get("text", ""),
        )

    @classmethod
    def _parse_file_item(cls, raw: dict[str, Any]) -> FileInfo:
        """Parse a file_item dict into FileInfo."""
        media = cls._parse_media_info(raw.get("media", {}))
        return FileInfo(
            media=media,
            file_name=raw.get("file_name", ""),
            file_size=str(raw.get("len", "")),
            md5=raw.get("md5", ""),
        )

    @classmethod
    def _parse_video_item(cls, raw: dict[str, Any]) -> VideoInfo:
        """Parse a video_item dict into VideoInfo."""
        media = cls._parse_media_info(raw.get("media", {}))
        return VideoInfo(
            media=media,
            play_length=raw.get("play_length", 0),
            video_md5=raw.get("video_md5", ""),
            thumb_width=raw.get("thumb_width", 0),
            thumb_height=raw.get("thumb_height", 0),
        )

    @staticmethod
    def _get_media_info(msg: Message) -> MediaInfo | None:
        """Extract MediaInfo from a message based on its type."""
        if msg.msg_type == MessageType.IMAGE and msg.image:
            return msg.image.media
        if msg.msg_type == MessageType.VOICE and msg.voice:
            return msg.voice.media
        if msg.msg_type == MessageType.FILE and msg.file:
            return msg.file.media
        if msg.msg_type == MessageType.VIDEO and msg.video:
            return msg.video.media
        return None

    def _send_media(
        self,
        to: str,
        file_data: bytes,
        media_type: UploadMediaType,
        item_key: str,
        file_name: str | None = None,
    ) -> bool:
        """Upload and send a media message.

        Args:
            to: Target user ID.
            file_data: Raw file bytes.
            media_type: Upload media type enum value.
            item_key: Item key in message body (e.g. "image_item").
            file_name: Original file name (for file_item only).

        Returns:
            True if sent successfully.
        """
        from weilink._cdn import upload_media

        self._ensure_connected()
        assert self._bot_info is not None

        ctx_token = self._context_tokens.get(to)
        if not ctx_token:
            logger.warning("No context_token for user %s, cannot send", to)
            return False

        def _get_url(**kwargs: Any) -> dict[str, Any]:
            assert self._bot_info is not None
            return proto.get_upload_url(
                **kwargs,
                token=self._bot_info.token,
                base_url=self._bot_info.base_url,
            )

        try:
            uploaded = upload_media(file_data, media_type.value, to, _get_url)

            # Build the media item
            # aes_key in protocol is base64(hex_string_as_ascii)
            aes_key_b64 = base64.b64encode(uploaded.aes_key_hex.encode()).decode()
            media_dict: dict[str, Any] = {
                "media": {
                    "encrypt_query_param": uploaded.download_param,
                    "aes_key": aes_key_b64,
                    "encrypt_type": 1,
                }
            }
            if item_key == "image_item":
                media_dict["mid_size"] = uploaded.cipher_size
            elif item_key == "video_item":
                media_dict["video_size"] = uploaded.cipher_size
            if file_name and item_key == "file_item":
                media_dict["file_name"] = file_name
                media_dict["len"] = str(uploaded.file_size)

            item_type_map = {
                "image_item": 2,
                "voice_item": 3,
                "file_item": 4,
                "video_item": 5,
            }
            item_list = [{"type": item_type_map[item_key], item_key: media_dict}]
            logger.debug("send media item_list: %s", item_list)

            resp = proto.send_media_message(
                to_user=to,
                item_list=item_list,
                context_token=ctx_token,
                token=self._bot_info.token,
                base_url=self._bot_info.base_url,
            )
            ret = resp.get("ret", 0)
            if ret != 0:
                logger.warning(
                    "send media to %s returned ret=%s: %s",
                    to,
                    ret,
                    resp.get("errmsg", ""),
                )
                return False
            return True
        except proto.ILinkError as e:
            logger.error("Failed to send media to %s: %s", to, e)
            return False

    def _set_typing(self, to: str, status: int) -> None:
        """Set or cancel typing indicator."""
        self._ensure_connected()
        assert self._bot_info is not None

        # Get typing ticket (cached per user)
        ticket = self._typing_tickets.get(to)
        if not ticket:
            ctx_token = self._context_tokens.get(to)
            try:
                config = proto.get_config(
                    user_id=to,
                    token=self._bot_info.token,
                    context_token=ctx_token,
                    base_url=self._bot_info.base_url,
                )
                ticket = config.get("typing_ticket", "")
                if ticket:
                    self._typing_tickets[to] = ticket
            except proto.ILinkError as e:
                logger.warning("Failed to get typing ticket for %s: %s", to, e)
                return

        if not ticket:
            return

        try:
            proto.send_typing(
                user_id=to,
                typing_ticket=ticket,
                status=status,
                token=self._bot_info.token,
                base_url=self._bot_info.base_url,
            )
        except proto.ILinkError as e:
            logger.warning("Failed to set typing for %s: %s", to, e)
