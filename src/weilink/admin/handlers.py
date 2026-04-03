"""HTTP request handlers for admin panel."""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import TYPE_CHECKING, Any, ClassVar

from weilink import __version__
from weilink.models import BotInfo

from .static import ADMIN_HTML, load_locale

if TYPE_CHECKING:
    from weilink.client import WeiLink

logger = logging.getLogger(__name__)


def _qr_to_svg(text: str) -> str:
    """Encode text as QR code and return an SVG string."""
    from weilink._vendor.qr import QrCode

    qr = QrCode.encode_text(text, QrCode.Ecc.LOW)
    size = qr.get_size()
    border = 2
    total = size + border * 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total}">',
        f'<rect width="{total}" height="{total}" fill="#fff"/>',
    ]
    for y in range(size):
        for x in range(size):
            if qr.get_module(x, y):
                parts.append(
                    f'<rect x="{x + border}" y="{y + border}" '
                    f'width="1" height="1" fill="#000"/>'
                )
    parts.append("</svg>")
    svg = "".join(parts)
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


class AdminRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the WeiLink admin panel."""

    weilink: ClassVar[WeiLink]
    _pending_logins: ClassVar[dict[str, dict[str, Any]]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP logging."""

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._handle_root()
        elif path == "/api/status":
            self._handle_status()
        elif path == "/api/sessions":
            self._handle_get_sessions()
        elif path == "/api/sessions/login/status":
            self._handle_poll_login(query)
        elif path.startswith("/api/messages/") and path.endswith("/download"):
            msg_id = path[len("/api/messages/") : -len("/download")]
            self._handle_download_media(msg_id)
        elif path == "/api/messages":
            self._handle_get_messages(query)
        elif path.startswith("/locales/") and path.endswith(".json"):
            lang = path[len("/locales/") : -len(".json")]
            self._handle_locale(lang)
        else:
            self._send_not_found()

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        if path == "/api/sessions/login":
            self._handle_start_login(body)
        elif path == "/api/set-default":
            self._handle_set_default(body)
        elif path.endswith("/logout"):
            name = path[len("/api/sessions/") : -len("/logout")]
            self._handle_logout(urllib.parse.unquote(name))
        elif path.endswith("/rename"):
            name = path[len("/api/sessions/") : -len("/rename")]
            self._handle_rename(urllib.parse.unquote(name), body)
        else:
            self._send_not_found()

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_root(self) -> None:
        """Serve the admin HTML page."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(ADMIN_HTML.encode("utf-8"))

    def _handle_status(self) -> None:
        """Return overall status."""
        wl = self.weilink
        self._send_json(
            {
                "version": __version__,
                "is_connected": wl.is_connected,
                "session_count": len(wl.sessions),
                "connected_count": sum(1 for s in wl._sessions.values() if s.bot_info),
            }
        )

    def _handle_get_sessions(self) -> None:
        """Return all sessions with user details."""
        wl = self.weilink
        now = time.time()
        expiry = 24 * 3600

        sessions = []
        for name, s in wl._sessions.items():
            users = []
            for user_id, token in s.context_tokens.items():
                ts = s.context_timestamps.get(user_id, 0.0)
                users.append(
                    {
                        "user_id": user_id,
                        "last_interaction": ts,
                        "fresh": (now - ts) < expiry if ts > 0 else False,
                        "last_sent": s.send_timestamps.get(user_id, 0.0),
                        "first_seen": s.user_first_seen.get(user_id, 0.0),
                    }
                )
            sessions.append(
                {
                    "name": name,
                    "bot_id": s.bot_info.bot_id if s.bot_info else None,
                    "user_id": s.bot_info.user_id if s.bot_info else None,
                    "connected": s.bot_info is not None,
                    "is_default": s is wl._default_session,
                    "created_at": s.created_at,
                    "user_count": len(users),
                    "users": users,
                }
            )

        self._send_json({"sessions": sessions})

    def _handle_start_login(self, body: bytes) -> None:
        """Start a QR code login flow."""
        from weilink import _protocol as proto

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON body")
            return

        name = data.get("name", "").strip()
        if not name:
            name = "default"

        # Check if session already connected
        wl = self.weilink
        if name in wl._sessions and wl._sessions[name].bot_info:
            self._send_error(
                409, f"Session {name!r} is already connected. Logout first."
            )
            return

        # Clean up stale pending logins (> 5 minutes)
        cutoff = time.time() - 300
        stale = [k for k, v in self._pending_logins.items() if v["started_at"] < cutoff]
        for k in stale:
            del self._pending_logins[k]

        try:
            qr_resp = proto.get_qr_code()
        except Exception as e:
            self._send_error(502, f"Failed to get QR code: {e}")
            return

        qrcode = qr_resp.get("qrcode", "")
        qr_url = qr_resp.get("qrcode_img_content", "")

        if not qrcode:
            self._send_error(502, "No QR code returned from server")
            return

        qr_svg = _qr_to_svg(qr_url) if qr_url else ""

        self._pending_logins[qrcode] = {
            "name": name,
            "started_at": time.time(),
        }

        self._send_json(
            {
                "qrcode": qrcode,
                "qr_url": qr_url,
                "qr_svg": qr_svg,
                "session_name": name,
            }
        )

    def _handle_poll_login(self, query: dict[str, list[str]]) -> None:
        """Poll QR code scan status."""
        from weilink import _protocol as proto

        qrcode = query.get("qrcode", [""])[0]
        if not qrcode or qrcode not in self._pending_logins:
            self._send_error(400, "Invalid or expired QR code")
            return

        pending = self._pending_logins[qrcode]

        try:
            status_resp = proto.poll_qr_status(qrcode)
        except Exception:
            self._send_json({"status": "waiting"})
            return

        status = status_resp.get("status", "")

        if status == "confirmed":
            bot_token = status_resp.get("bot_token", "")
            base_url = status_resp.get("baseurl", proto.BASE_URL)
            bot_id = status_resp.get("ilink_bot_id", "")
            user_id = status_resp.get("ilink_user_id", "")
            name = pending["name"]

            with self._lock:
                wl = self.weilink
                if name in wl._sessions:
                    session = wl._sessions[name]
                else:
                    token_path = wl._base_path / name / "token.json"
                    session = wl._create_session(name, token_path)

                session.bot_info = BotInfo(
                    bot_id=bot_id,
                    base_url=base_url,
                    token=bot_token,
                    user_id=user_id,
                )
                session.cursor = ""
                wl._save_session_state(session)

            del self._pending_logins[qrcode]
            self._send_json(
                {
                    "status": "confirmed",
                    "bot_id": bot_id,
                    "session_name": name,
                }
            )

        elif status == "scaned":
            self._send_json({"status": "scaned"})

        elif status == "expired":
            del self._pending_logins[qrcode]
            self._send_json({"status": "expired"})

        else:
            self._send_json({"status": "waiting"})

    def _handle_logout(self, name: str) -> None:
        """Logout a session."""
        try:
            with self._lock:
                self.weilink.logout(name if name != "default" else None)
            self._send_json(
                {"success": True, "message": f"Session {name!r} logged out"}
            )
        except ValueError as e:
            self._send_error(404, str(e))

    def _handle_rename(self, name: str, body: bytes) -> None:
        """Rename a session."""
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON body")
            return

        new_name = data.get("new_name", "").strip()
        if not new_name:
            self._send_error(400, "new_name is required")
            return

        try:
            with self._lock:
                self.weilink.rename_session(name, new_name)
            self._send_json(
                {
                    "success": True,
                    "message": f"Session renamed: {name!r} -> {new_name!r}",
                }
            )
        except ValueError as e:
            self._send_error(400, str(e))

    def _handle_set_default(self, body: bytes) -> None:
        """Set a session as the default."""
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON body")
            return

        name = data.get("name", "").strip()
        if not name:
            self._send_error(400, "name is required")
            return

        try:
            with self._lock:
                self.weilink.set_default(name)
            self._send_json(
                {
                    "success": True,
                    "message": f"Default session set to {name!r}",
                }
            )
        except ValueError as e:
            self._send_error(404, str(e))

    def _handle_get_messages(self, query: dict[str, list[str]]) -> None:
        """Return paginated message history as JSON."""
        store = self.weilink._message_store
        if store is None:
            self._send_error(400, "Message persistence is not enabled")
            return

        kwargs: dict[str, Any] = {}
        if "user_id" in query:
            kwargs["user_id"] = query["user_id"][0]
        if "bot_id" in query:
            kwargs["bot_id"] = query["bot_id"][0]
        if "msg_type" in query:
            kwargs["msg_type"] = int(query["msg_type"][0])
        if "direction" in query:
            kwargs["direction"] = int(query["direction"][0])
        if "text_contains" in query:
            kwargs["text_contains"] = query["text_contains"][0]

        limit = min(int(query.get("limit", ["30"])[0]), 200)
        offset = int(query.get("offset", ["0"])[0])

        total = store.count(**kwargs)
        messages = store.query(**kwargs, limit=limit, offset=offset)
        # Convert message_id to string to avoid JS integer precision loss
        for m in messages:
            if "message_id" in m:
                m["message_id"] = str(m["message_id"])
        self._send_json({"messages": messages, "total": total})

    _MIME_MAP: ClassVar[dict[str, str]] = {
        "IMAGE": "image/jpeg",
        "VOICE": "audio/amr",
        "VIDEO": "video/mp4",
    }
    _EXT_MAP: ClassVar[dict[str, str]] = {
        "IMAGE": ".jpg",
        "VOICE": ".amr",
        "VIDEO": ".mp4",
    }

    def _handle_download_media(self, message_id_str: str) -> None:
        """Download media from a stored message and serve the bytes."""
        store = self.weilink._message_store
        if store is None:
            self._send_error(400, "Message persistence is not enabled")
            return

        try:
            msg = store.get_by_id(int(message_id_str))
        except (ValueError, TypeError):
            msg = None
        if msg is None:
            self._send_error(404, f"Message {message_id_str} not found")
            return

        try:
            data = self.weilink.download(msg)
        except ValueError as e:
            self._send_error(400, str(e))
            return
        except Exception as e:
            self._send_error(502, f"Download failed: {e}")
            return

        # Derive filename and MIME type
        mt = msg.msg_type.name
        if msg.file and msg.file.file_name:
            filename = msg.file.file_name
        else:
            ext = self._EXT_MAP.get(mt, ".bin")
            filename = f"{msg.message_id}{ext}"
        content_type = self._MIME_MAP.get(mt, "application/octet-stream")

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _handle_locale(self, lang: str) -> None:
        """Serve a locale JSON file."""
        content = load_locale(lang)
        if content is None:
            self._send_not_found()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _send_cors_headers(self) -> None:
        """Send CORS headers."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send a JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_error(self, status: int, message: str) -> None:
        """Send a JSON error response."""
        self._send_json({"error": message}, status)

    def _send_not_found(self) -> None:
        """Send 404."""
        self._send_error(404, f"Not found: {self.path}")
