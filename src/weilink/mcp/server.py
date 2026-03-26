"""MCP / OpenAPI server exposing WeiLink bot capabilities as tools.

Uses ``toolregistry`` + ``toolregistry-server`` to define tools once and
expose them via both MCP and OpenAPI protocols.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Literal

from weilink import Message, MessageType, WeiLink
from weilink._protocol import ILinkError, SessionExpiredError

logger = logging.getLogger(__name__)

_MAX_CACHE = 1000
_DEFAULT_DOWNLOAD_DIR = Path.home() / ".weilink" / "downloads"

# Global state — initialized lazily on first tool call.
_wl: WeiLink | None = None
_message_cache: OrderedDict[str, Message] = OrderedDict()
_pending_login: dict[str, Any] | None = None


def _init_client(base_path: Path | None = None) -> None:
    """Pre-initialize the global WeiLink client with optional *base_path*."""
    global _wl
    if _wl is None:
        kwargs: dict[str, Any] = {}
        if base_path is not None:
            kwargs["base_path"] = base_path
        _wl = WeiLink(**kwargs)


def _get_client() -> WeiLink:
    """Return the global WeiLink client, creating it on first use."""
    global _wl
    if _wl is None:
        _wl = WeiLink()
    return _wl


def _cache_messages(messages: list[Message]) -> None:
    """Add messages to the cache, evicting oldest when over limit."""
    for msg in messages:
        key = str(msg.message_id)
        _message_cache[key] = msg
    while len(_message_cache) > _MAX_CACHE:
        _message_cache.popitem(last=False)


def _serialize_message(msg: Message) -> dict[str, Any]:
    """Convert a Message to a JSON-friendly dict."""
    result: dict[str, Any] = {
        "message_id": msg.message_id,
        "from_user": msg.from_user,
        "msg_type": msg.msg_type.name,
        "timestamp": msg.timestamp,
        "bot_id": msg.bot_id,
    }
    if msg.text is not None:
        result["text"] = msg.text
    if msg.image is not None:
        result["image"] = {
            "url": msg.image.url,
            "thumb_width": msg.image.thumb_width,
            "thumb_height": msg.image.thumb_height,
        }
    if msg.voice is not None:
        result["voice"] = {
            "playtime": msg.voice.playtime,
            "text": msg.voice.text,
        }
    if msg.file is not None:
        result["file"] = {
            "file_name": msg.file.file_name,
            "file_size": msg.file.file_size,
        }
    if msg.video is not None:
        result["video"] = {
            "play_length": msg.video.play_length,
            "thumb_width": msg.video.thumb_width,
            "thumb_height": msg.video.thumb_height,
        }
    if msg.ref_msg is not None:
        ref: dict[str, Any] = {"msg_type": msg.ref_msg.msg_type.name}
        if msg.ref_msg.text is not None:
            ref["text"] = msg.ref_msg.text
        if msg.ref_msg.image is not None:
            ref["image"] = {
                "url": msg.ref_msg.image.url,
                "thumb_width": msg.ref_msg.image.thumb_width,
                "thumb_height": msg.ref_msg.image.thumb_height,
            }
        if msg.ref_msg.voice is not None:
            ref["voice"] = {
                "playtime": msg.ref_msg.voice.playtime,
                "text": msg.ref_msg.voice.text,
            }
        if msg.ref_msg.file is not None:
            ref["file"] = {
                "file_name": msg.ref_msg.file.file_name,
                "file_size": msg.ref_msg.file.file_size,
            }
        if msg.ref_msg.video is not None:
            ref["video"] = {
                "play_length": msg.ref_msg.video.play_length,
                "thumb_width": msg.ref_msg.video.thumb_width,
                "thumb_height": msg.ref_msg.video.thumb_height,
            }
        result["ref_msg"] = ref
    return result


# ------------------------------------------------------------------
# Tool functions (registered via toolregistry)
# ------------------------------------------------------------------


async def recv_messages(timeout: float = 5.0) -> str:
    """Receive new messages from WeChat users.

    Long-polls all active sessions and returns any pending messages.
    Received messages are cached so their media can be downloaded later
    via download_media.

    Args:
        timeout: Maximum wait time in seconds (default 5).

    Returns:
        JSON array of message objects.
    """
    wl = _get_client()
    if not wl.is_connected:
        return json.dumps({"error": "Not logged in. Use login tool first."})

    try:
        messages = await asyncio.to_thread(wl.recv, timeout=timeout)
    except SessionExpiredError:
        return json.dumps({"error": "Session expired. Please re-login."})
    except (TimeoutError, OSError):
        messages = []
    except RuntimeError as e:
        return json.dumps({"error": str(e)})

    _cache_messages(messages)
    return json.dumps([_serialize_message(m) for m in messages])


async def send_message(
    to: str,
    text: str = "",
    image_path: str = "",
    file_path: str = "",
    file_name: str = "",
    video_path: str = "",
    voice_path: str = "",
) -> str:
    """Send a message to a WeChat user.

    At least one of text, image_path, file_path, video_path, or voice_path
    must be provided.

    Args:
        to: Target user ID (e.g. xxx@im.wechat).
        text: Text message content.
        image_path: Local path to an image file.
        file_path: Local path to a file attachment.
        file_name: Display name for the file (defaults to filename from path).
        video_path: Local path to a video file.
        voice_path: Local path to a voice file.

    Returns:
        JSON with success status and details.
    """
    wl = _get_client()
    if not wl.is_connected:
        return json.dumps({"error": "Not logged in. Use login tool first."})

    kwargs: dict[str, Any] = {}
    if text:
        kwargs["text"] = text

    if image_path:
        p = Path(image_path)
        if not p.is_file():
            return json.dumps({"error": f"Image file not found: {image_path}"})
        kwargs["image"] = p.read_bytes()

    if voice_path:
        p = Path(voice_path)
        if not p.is_file():
            return json.dumps({"error": f"Voice file not found: {voice_path}"})
        kwargs["voice"] = p.read_bytes()

    if file_path:
        p = Path(file_path)
        if not p.is_file():
            return json.dumps({"error": f"File not found: {file_path}"})
        kwargs["file"] = p.read_bytes()
        kwargs["file_name"] = file_name or p.name

    if video_path:
        p = Path(video_path)
        if not p.is_file():
            return json.dumps({"error": f"Video file not found: {video_path}"})
        kwargs["video"] = p.read_bytes()

    if not kwargs:
        return json.dumps({"error": "No content provided."})

    try:
        result = await asyncio.to_thread(wl.send, to, auto_recv=True, **kwargs)
    except (RuntimeError, ValueError) as e:
        return json.dumps({"error": str(e)})

    # Cache any messages received during auto-recv
    if result.messages:
        _cache_messages(result.messages)

    response: dict[str, Any] = {"success": result.success}
    if result.messages:
        response["new_messages"] = [_serialize_message(m) for m in result.messages]
    return json.dumps(response)


async def download_media(message_id: str, save_dir: str = "") -> str:
    """Download media from a previously received message.

    The message must have been received via recv_messages in this session.

    Args:
        message_id: Message ID from the recv_messages output.
        save_dir: Directory to save the file (default ~/.weilink/downloads/).

    Returns:
        JSON with saved file path and size in bytes.
    """
    msg = _message_cache.get(message_id)
    if msg is None:
        return json.dumps(
            {
                "error": f"Message {message_id} not found in cache. "
                "Receive it first via recv_messages."
            }
        )

    wl = _get_client()
    try:
        data = await asyncio.to_thread(wl.download, msg)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Determine file name
    name = _media_filename(msg)
    out_dir = Path(save_dir) if save_dir else _DEFAULT_DOWNLOAD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / name

    # Avoid overwriting
    if out_path.exists():
        stem, suffix = out_path.stem, out_path.suffix
        out_path = out_dir / f"{stem}_{int(time.time())}{suffix}"

    out_path.write_bytes(data)
    return json.dumps({"path": str(out_path), "size": len(data)})


def _media_filename(msg: Message) -> str:
    """Derive a reasonable file name from a media message."""
    ext_map = {
        MessageType.IMAGE: ".jpg",
        MessageType.VOICE: ".amr",
        MessageType.VIDEO: ".mp4",
    }
    if msg.file and msg.file.file_name:
        return msg.file.file_name
    ext = ext_map.get(msg.msg_type, ".bin")
    return f"{msg.message_id}{ext}"


def list_sessions() -> str:
    """List all WeiLink sessions and their connection status.

    Returns:
        JSON array of session objects with name, bot_id, and connected status.
    """
    wl = _get_client()
    sessions = []
    for name in wl.sessions:
        bot_ids = wl.bot_ids
        sessions.append(
            {
                "name": name,
                "bot_id": bot_ids.get(name),
                "connected": name in bot_ids,
            }
        )
    return json.dumps(sessions)


async def login(session_name: str = "") -> str:
    """Start a QR code login flow.

    Returns a QR code URL that the user must open in a browser and scan
    with WeChat. After scanning, call check_login to confirm.

    Args:
        session_name: Optional session name for multi-account support.
            Leave empty for the default session.

    Returns:
        JSON with qr_url for the user to scan.
    """
    global _pending_login
    from weilink import _protocol as proto

    try:
        qr_resp = await asyncio.to_thread(proto.get_qr_code)
    except ILinkError as e:
        return json.dumps({"error": f"Failed to get QR code: {e}"})

    qrcode = qr_resp.get("qrcode", "")
    qr_url = qr_resp.get("qrcode_img_content", "")

    _pending_login = {
        "qrcode": qrcode,
        "session_name": session_name or None,
        "created_at": time.time(),
    }

    return json.dumps(
        {
            "status": "pending",
            "qr_url": qr_url,
            "message": "Open the QR code URL in a browser and scan with WeChat.",
        }
    )


async def check_login() -> str:
    """Check the status of a pending QR code login.

    Must be called after login. Polls the server once and returns
    the current status. Call repeatedly until status is 'confirmed'
    or 'expired'.

    Returns:
        JSON with status (pending/scanned/confirmed/expired) and details.
    """
    global _pending_login
    if _pending_login is None:
        return json.dumps({"error": "No pending login. Call login first."})

    from weilink import _protocol as proto

    qrcode = _pending_login["qrcode"]
    session_name = _pending_login["session_name"]

    # Timeout after 5 minutes
    if time.time() - _pending_login["created_at"] > 300:
        _pending_login = None
        return json.dumps({"status": "expired", "message": "Login timed out."})

    try:
        status_resp = await asyncio.to_thread(proto.poll_qr_status, qrcode)
    except (ILinkError, TimeoutError, OSError) as e:
        return json.dumps({"status": "pending", "message": f"Poll error: {e}"})

    status = status_resp.get("status", "")

    if status == "confirmed":
        wl = _get_client()
        bot_token = status_resp.get("bot_token", "")
        base_url = status_resp.get("baseurl", proto.BASE_URL)
        bot_id = status_resp.get("ilink_bot_id", "")

        # Use the public login API to properly initialize session state.
        # Since we already confirmed, calling login() would try to start
        # a new QR flow. Instead, we manually set up the session via the
        # internal interface that login() uses.
        from weilink.models import BotInfo

        name = session_name or "default"
        if name == "default":
            session = wl._default_session
        elif name in wl._sessions:
            session = wl._sessions[name]
        else:
            token_path = wl._base_path / name / "token.json"
            session = wl._create_session(name, token_path)

        session.bot_info = BotInfo(bot_id=bot_id, base_url=base_url, token=bot_token)
        session.cursor = ""
        wl._save_session_state(session)

        _pending_login = None
        return json.dumps(
            {
                "status": "confirmed",
                "bot_id": bot_id,
                "session": name,
                "message": "Login successful!",
            }
        )

    if status == "scaned":
        return json.dumps(
            {
                "status": "scanned",
                "message": "QR code scanned. Waiting for confirmation on phone.",
            }
        )

    if status == "expired":
        _pending_login = None
        return json.dumps(
            {
                "status": "expired",
                "message": "QR code expired. Call login again to get a new one.",
            }
        )

    # Protocol returns "wait" when no scan yet; map to "pending" for MCP output.
    return json.dumps({"status": "pending", "message": "Waiting for scan..."})


# ------------------------------------------------------------------
# Registry and server entry points
# ------------------------------------------------------------------

_TOOL_FUNCTIONS = [
    recv_messages,
    send_message,
    download_media,
    list_sessions,
    login,
    check_login,
]


def build_registry():
    """Build a ToolRegistry with all WeiLink tool functions.

    Returns:
        A configured ToolRegistry instance.
    """
    from toolregistry import ToolRegistry

    registry = ToolRegistry(name="weilink")
    for fn in _TOOL_FUNCTIONS:
        registry.register(fn)
    return registry


def run_mcp(
    transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    base_path: Path | None = None,
) -> None:
    """Run the MCP server with the specified transport.

    Args:
        transport: One of ``"stdio"``, ``"sse"``, ``"streamable-http"``.
        host: Host address for SSE / streamable-http transports.
        port: Port for SSE / streamable-http transports.
        base_path: Optional WeiLink data directory.
    """
    from toolregistry_server import RouteTable
    from toolregistry_server.mcp import (
        create_mcp_server,
        run_sse,
        run_stdio,
        run_streamable_http,
    )

    _init_client(base_path)
    route_table = RouteTable(build_registry())
    server = create_mcp_server(route_table, name="weilink")

    if transport == "stdio":
        asyncio.run(run_stdio(server))
    elif transport == "sse":
        asyncio.run(run_sse(server, host=host, port=port))
    else:
        asyncio.run(run_streamable_http(server, host=host, port=port))


def run_openapi(
    host: str = "127.0.0.1",
    port: int = 8000,
    base_path: Path | None = None,
) -> None:
    """Run the OpenAPI server.

    Args:
        host: Host address to bind to.
        port: Port to bind to.
        base_path: Optional WeiLink data directory.
    """
    import uvicorn
    from toolregistry_server import RouteTable
    from toolregistry_server.openapi import create_openapi_app

    _init_client(base_path)
    route_table = RouteTable(build_registry())
    app = create_openapi_app(
        route_table,
        title="WeiLink",
        description="WeiLink Bot API Tools",
    )
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    """Run the WeiLink MCP server (stdio transport)."""
    run_mcp(transport="stdio")
