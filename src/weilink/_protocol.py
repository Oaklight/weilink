"""Internal iLink Bot protocol implementation.

Handles HTTP communication, header construction, and endpoint definitions.
Not part of the public API.
"""

from __future__ import annotations

import base64
import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# iLink API endpoints
BASE_URL = "https://ilinkai.weixin.qq.com"
EP_QR_CODE = "/ilink/bot/get_bot_qrcode"
EP_QR_STATUS = "/ilink/bot/get_qrcode_status"
EP_GET_UPDATES = "/ilink/bot/getupdates"
EP_SEND_MESSAGE = "/ilink/bot/sendmessage"
EP_GET_UPLOAD_URL = "/ilink/bot/getuploadurl"
EP_GET_CONFIG = "/ilink/bot/getconfig"
EP_SEND_TYPING = "/ilink/bot/sendtyping"

# Protocol constants
BOT_TYPE = 3
CHANNEL_VERSION = "1.0.2"
LONGPOLL_TIMEOUT = 35.0
SESSION_EXPIRED = -14
CONTEXT_TOKEN_QUOTA = 10  # max outbound messages per context_token
TEXT_BYTE_LIMIT = 16384  # 16 KiB UTF-8, server rejects texts above this


class ILinkError(Exception):
    """Error from the iLink API."""

    def __init__(self, ret: int, errcode: int | None = None, errmsg: str = ""):
        self.ret = ret
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"iLink error: ret={ret}, errcode={errcode}, msg={errmsg}")


class SessionExpiredError(ILinkError):
    """Session expired, re-login required."""


class QuotaExhaustedError(ILinkError):
    """Context token send quota (10 messages) exhausted.

    The user must send a new message to obtain a fresh context_token
    before the bot can send more replies.
    """


class TextTooLongError(ILinkError):
    """Text exceeds the 16 KiB UTF-8 byte limit after splitting."""


def _random_uin() -> str:
    """Generate a random X-WECHAT-UIN header value.

    Each request uses a fresh random uint32, base64-encoded.
    """
    val = random.randint(0, 0xFFFFFFFF)
    return base64.b64encode(str(val).encode()).decode()


def _make_headers(token: str | None = None) -> dict[str, str]:
    """Build common iLink request headers."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_uin(),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def post(
    endpoint: str,
    body: dict[str, Any],
    token: str,
    base_url: str = BASE_URL,
    timeout: float = LONGPOLL_TIMEOUT,
) -> dict[str, Any]:
    """POST JSON to an iLink endpoint.

    Args:
        endpoint: API path (e.g. "/ilink/bot/getupdates").
        body: Request body as a dict.
        token: Bot bearer token.
        base_url: API base URL.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        ILinkError: If the API returns a non-zero ret code.
        SessionExpiredError: If the session has expired (errcode -14).
    """
    url = f"{base_url}{endpoint}"
    data = json.dumps(body).encode()
    headers = _make_headers(token)

    logger.debug("POST %s (timeout=%.1fs, body_len=%d)", url, timeout, len(data))

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            result: dict[str, Any] = json.loads(raw)
            logger.debug(
                "POST %s -> HTTP %s, resp_len=%d, ret=%s",
                endpoint,
                resp.status,
                len(raw),
                result.get("ret", "?"),
            )
    except urllib.error.URLError as e:
        logger.warning("POST %s failed: %s", endpoint, e)
        raise ILinkError(ret=-1, errmsg=str(e)) from e

    ret = result.get("ret", 0)
    errcode = result.get("errcode")

    if errcode == SESSION_EXPIRED:
        logger.warning("Session expired on %s (ret=%s)", endpoint, ret)
        raise SessionExpiredError(
            ret=ret, errcode=errcode, errmsg=result.get("errmsg", "session expired")
        )

    if ret != 0:
        logger.warning(
            "POST %s non-zero ret=%s, errcode=%s, errmsg=%s",
            endpoint,
            ret,
            errcode,
            result.get("errmsg", ""),
        )

    return result


def get(
    endpoint: str,
    params: dict[str, str] | None = None,
    token: str | None = None,
    base_url: str = BASE_URL,
    timeout: float = 10.0,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """GET from an iLink endpoint.

    Args:
        endpoint: API path (e.g. "/ilink/bot/get_bot_qrcode").
        params: Query parameters.
        token: Bot bearer token (optional for login endpoints).
        base_url: API base URL.
        timeout: Request timeout in seconds.
        extra_headers: Additional headers to include in the request.

    Returns:
        Parsed JSON response as a dict.
    """
    url = f"{base_url}{endpoint}"
    if params:
        query = urllib.parse.urlencode(params)
        url = f"{url}?{query}"

    headers = _make_headers(token)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result: dict[str, Any] = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise ILinkError(ret=-1, errmsg=str(e)) from e

    return result


def get_qr_code(base_url: str = BASE_URL) -> dict[str, Any]:
    """Request a QR code for login.

    Returns:
        Dict with 'qrcode' (code string) and 'qrcode_img_content' (optional).
    """
    return get(EP_QR_CODE, params={"bot_type": str(BOT_TYPE)}, base_url=base_url)


def poll_qr_status(qrcode: str, base_url: str = BASE_URL) -> dict[str, Any]:
    """Poll QR code scan status.

    Returns:
        Dict with 'status', and on success: 'bot_token', 'baseurl'.
    """
    return get(
        EP_QR_STATUS,
        params={"qrcode": qrcode},
        base_url=base_url,
        timeout=40.0,
        extra_headers={"iLink-App-ClientVersion": "1"},
    )


def get_updates(
    cursor: str,
    token: str,
    base_url: str = BASE_URL,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Long-poll for new messages.

    Args:
        cursor: Sync cursor from previous response (empty string for first call).
        token: Bot bearer token.
        base_url: API base URL.
        timeout: HTTP timeout in seconds.  Defaults to ``LONGPOLL_TIMEOUT + 5``
            (40 s) which is long enough for the server-side long-poll to
            complete.  Pass a shorter value (e.g. 5) for quick, non-blocking
            checks.

    Returns:
        Dict with 'msgs', 'get_updates_buf', etc.
    """
    if timeout is None:
        timeout = LONGPOLL_TIMEOUT + 5
    body = {
        "get_updates_buf": cursor,
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    logger.debug(
        "get_updates: cursor=%s, timeout=%.1fs",
        cursor[:32] + "..." if len(cursor) > 32 else cursor or "(empty)",
        timeout,
    )
    result = post(EP_GET_UPDATES, body, token, base_url, timeout=timeout)
    msgs = result.get("msgs", [])
    new_cursor = result.get("get_updates_buf", "")
    lp_ms = result.get("longpolling_timeout_ms")
    logger.info(
        "get_updates: %d msg(s), new_cursor=%s, longpoll_ms=%s",
        len(msgs),
        new_cursor[:32] + "..." if len(new_cursor) > 32 else new_cursor or "(empty)",
        lp_ms,
    )
    if msgs:
        for i, m in enumerate(msgs):
            logger.debug(
                "  msg[%d]: type=%s, from=%s, keys=%s",
                i,
                m.get("message_type"),
                m.get("from_user_id", "?"),
                list(m.keys()),
            )
    return result


def send_message(
    to_user: str,
    text: str,
    context_token: str,
    token: str,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Send a single text message.

    Args:
        to_user: Target user ID (xxx@im.wechat).
        text: Message text (must be <= 16 KiB UTF-8).
        context_token: Context token from a received message.
        token: Bot bearer token.
        base_url: API base URL.
    """
    client_id = f"weilink:{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    body = {
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user,
            "client_id": client_id,
            "message_type": 2,  # BOT
            "message_state": 2,  # FINISH
            "context_token": context_token,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        },
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    return post(EP_SEND_MESSAGE, body, token, base_url, timeout=10.0)


def get_config(
    user_id: str,
    token: str,
    context_token: str | None = None,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Get account config (typing ticket).

    Args:
        user_id: Target user ID.
        token: Bot bearer token.
        context_token: Optional conversation context token.
        base_url: API base URL.
    """
    body: dict[str, Any] = {
        "ilink_user_id": user_id,
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    if context_token:
        body["context_token"] = context_token
    return post(EP_GET_CONFIG, body, token, base_url, timeout=10.0)


def send_typing(
    user_id: str,
    typing_ticket: str,
    status: int,
    token: str,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Send or cancel typing indicator.

    Args:
        user_id: Target user ID.
        typing_ticket: Ticket from get_config.
        status: 1 = typing, 2 = cancel.
        token: Bot bearer token.
        base_url: API base URL.
    """
    body = {
        "ilink_user_id": user_id,
        "typing_ticket": typing_ticket,
        "status": status,
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    return post(EP_SEND_TYPING, body, token, base_url, timeout=10.0)


def send_media_message(
    to_user: str,
    item_list: list[dict[str, Any]],
    context_token: str,
    token: str,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Send a message with arbitrary item_list (text, image, voice, file, video).

    Args:
        to_user: Target user ID (xxx@im.wechat).
        item_list: List of item dicts, e.g. [{"type": 2, "image_item": {...}}].
        context_token: Context token from a received message.
        token: Bot bearer token.
        base_url: API base URL.
    """
    client_id = f"weilink:{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    body = {
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user,
            "client_id": client_id,
            "message_type": 2,  # BOT
            "message_state": 2,  # FINISH
            "context_token": context_token,
            "item_list": item_list,
        },
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    return post(EP_SEND_MESSAGE, body, token, base_url, timeout=10.0)


def get_upload_url(
    file_md5: str,
    file_size: int,
    cipher_size: int,
    media_type: int,
    to_user_id: str,
    filekey: str,
    aes_key_hex: str,
    token: str,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Get a pre-signed CDN upload URL.

    Args:
        file_md5: MD5 hex digest of the original file.
        file_size: Original file size in bytes.
        cipher_size: Encrypted file size in bytes.
        media_type: Upload media type (1=IMAGE, 2=VIDEO, 3=FILE, 4=VOICE).
        to_user_id: Target user ID.
        filekey: Random hex filekey for this upload.
        aes_key_hex: Hex-encoded AES key used for encryption.
        token: Bot bearer token.
        base_url: API base URL.

    Returns:
        Dict with 'upload_url' and other metadata.
    """
    body = {
        "to_user_id": to_user_id,
        "media_type": media_type,
        "rawfilemd5": file_md5,
        "rawsize": file_size,
        "filesize": cipher_size,
        "filekey": filekey,
        "aeskey": aes_key_hex,
        "no_need_thumb": True,
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    return post(EP_GET_UPLOAD_URL, body, token, base_url, timeout=15.0)
