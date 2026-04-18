"""Shared constants and helpers used across CLI, server, and admin."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from weilink.models import BotInfo, Message, MessageDirection, MessageType

logger = logging.getLogger(__name__)


# -- Media constants ---------------------------------------------------------

MEDIA_EXT_MAP: dict[MessageType, str] = {
    MessageType.IMAGE: ".jpg",
    MessageType.VOICE: ".amr",
    MessageType.VIDEO: ".mp4",
}

MEDIA_MIME_MAP: dict[MessageType, str] = {
    MessageType.IMAGE: "image/jpeg",
    MessageType.VOICE: "audio/amr",
    MessageType.VIDEO: "video/mp4",
}


# -- QR login ----------------------------------------------------------------


@dataclass(frozen=True)
class QRResult:
    """Result of interpreting a ``poll_qr_status`` response.

    Attributes:
        status: Normalized status string — one of
            ``"confirmed"``, ``"scanned"``, ``"expired"``, or ``"waiting"``.
        bot_info: Populated only when *status* is ``"confirmed"``.
    """

    status: str
    bot_info: BotInfo | None = None


def process_qr_status(status_resp: dict[str, Any]) -> QRResult:
    """Interpret a raw ``poll_qr_status`` response.

    Args:
        status_resp: Dict returned by ``_protocol.poll_qr_status()``.

    Returns:
        A :class:`QRResult` with normalized status and, on confirmation,
        the extracted :class:`BotInfo`.
    """
    from weilink._protocol import BASE_URL

    status = status_resp.get("status", "")

    if status == "confirmed":
        bot_info = BotInfo(
            bot_id=status_resp.get("ilink_bot_id", ""),
            base_url=status_resp.get("baseurl", BASE_URL),
            token=status_resp.get("bot_token", ""),
            user_id=status_resp.get("ilink_user_id", ""),
        )
        return QRResult(status="confirmed", bot_info=bot_info)

    if status == "scaned":
        return QRResult(status="scanned")

    if status == "expired":
        return QRResult(status="expired")

    # Log unrecognized statuses (e.g. scaned_but_redirect) for investigation.
    if status and status not in ("waiting", ""):
        logger.debug(
            "Unrecognized QR status %r, full response: %s",
            status,
            status_resp,
        )

    return QRResult(status="waiting")


# -- Media helpers -----------------------------------------------------------


def media_filename(msg: Message) -> str:
    """Derive a filename for a media message.

    Uses the original ``file_name`` when available, otherwise falls back
    to ``{message_id}{ext}`` using :data:`MEDIA_EXT_MAP`.
    """
    if msg.file and msg.file.file_name:
        return msg.file.file_name
    ext = MEDIA_EXT_MAP.get(msg.msg_type, ".bin")
    return f"{msg.message_id}{ext}"


# -- Parsing helpers ---------------------------------------------------------


def parse_direction(s: str) -> int | None:
    """Parse a direction string to its integer value.

    Returns:
        ``MessageDirection.USER`` (1) for ``"received"``,
        ``MessageDirection.BOT`` (2) for ``"sent"``,
        or ``None`` for unrecognized input.
    """
    d = s.lower()
    if d == "received":
        return MessageDirection.USER
    if d == "sent":
        return MessageDirection.BOT
    return None


def parse_message_type(s: str) -> int | None:
    """Parse a message type name to its integer value.

    Returns:
        The ``MessageType`` integer (e.g. 2 for ``"IMAGE"``),
        or ``None`` for unrecognized input.
    """
    try:
        return MessageType[s.upper()].value
    except KeyError:
        return None


def parse_time(s: str) -> int | None:
    """Parse an ISO 8601 string or unix milliseconds to *int* milliseconds.

    Returns:
        Millisecond timestamp, or ``None`` on failure.
    """
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None
