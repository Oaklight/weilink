"""WeiLink client - public API for WeChat iLink Bot protocol."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from weilink import _protocol as proto
from weilink.models import BotInfo, Message, MessageType

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
        self._typing_tickets: dict[str, str] = {}
        self._load_state()

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
                messages.append(msg)

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

        # Try segno (pure Python, no deps)
        try:
            import segno

            qr = segno.make(url)
            qr.terminal(compact=True)
            return
        except ImportError:
            pass

        # Try qrcode
        try:
            import qrcode as qr_lib

            q = qr_lib.QRCode(border=1)
            q.add_data(url)
            q.print_ascii(invert=True)
            return
        except ImportError:
            pass

        print("(Install 'segno' or 'qrcode' for terminal QR display)\n")

    def _ensure_connected(self) -> None:
        """Raise if not logged in."""
        if not self._bot_info:
            raise RuntimeError("Not logged in. Call login() first.")

    def _parse_message(self, raw: dict[str, Any]) -> Message | None:
        """Parse a raw iLink message dict into a Message."""
        from_user = raw.get("from_user_id", "")
        if not from_user:
            return None

        # Extract text from item_list
        text: str | None = None
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

        return Message(
            from_user=from_user,
            text=text,
            msg_type=msg_type,
            timestamp=raw.get("create_time_ms", 0),
            message_id=raw.get("message_id"),
            context_token=raw.get("context_token", ""),
        )

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
