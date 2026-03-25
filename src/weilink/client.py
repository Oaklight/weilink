"""WeiLink client - public API for WeChat iLink Bot protocol."""

from __future__ import annotations

import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
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
    SendMediaType,
    UploadMediaType,
    UploadedMedia,
    VideoInfo,
    VoiceInfo,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_PATH = Path.home() / ".weilink"
_DEFAULT_SESSION = "default"


@dataclass
class _Session:
    """Per-session state for a single bot registration."""

    name: str
    token_path: Path
    bot_info: BotInfo | None = None
    cursor: str = ""
    context_tokens: dict[str, str] = field(default_factory=dict)
    context_timestamps: dict[str, float] = field(default_factory=dict)
    typing_tickets: dict[str, str] = field(default_factory=dict)

    @property
    def contexts_path(self) -> Path:
        """Path to the contexts persistence file (sibling to token.json)."""
        return self.token_path.parent / "contexts.json"


class WeiLink:
    """Lightweight WeChat iLink Bot client.

    Supports multiple named sessions for registering one bot with multiple
    WeChat accounts.  When ``name`` is not provided, a default session is
    used and behaviour is identical to single-session usage.

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

    def __init__(
        self,
        token_path: str | Path | None = None,
        *,
        base_path: str | Path | None = None,
    ):
        """Initialize the WeiLink client.

        Args:
            token_path: Path to persist bot credentials for the default
                session.  Defaults to ``~/.weilink/token.json``.
            base_path: Base directory for multi-session storage.  Named
                sessions are stored under ``<base_path>/<name>/``.
                Defaults to ``~/.weilink/``.  Ignored if *token_path*
                is given (the base path is derived from it).
        """
        if token_path is not None:
            self._base_path = Path(token_path).parent
        elif base_path is not None:
            self._base_path = Path(base_path)
        else:
            self._base_path = _DEFAULT_BASE_PATH

        default_token = (
            Path(token_path) if token_path else self._base_path / "token.json"
        )

        self._sessions: dict[str, _Session] = {}
        self._default_session = self._create_session(_DEFAULT_SESSION, default_token)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _create_session(self, name: str, token_path: Path) -> _Session:
        """Create a session, load its persisted state, and register it."""
        session = _Session(name=name, token_path=token_path)
        self._load_session_state(session)
        self._load_session_contexts(session)
        self._sessions[name] = session
        return session

    def _session_for_name(self, name: str | None) -> _Session:
        """Resolve a session by name, falling back to default."""
        key = name or _DEFAULT_SESSION
        session = self._sessions.get(key)
        if session is None:
            raise ValueError(
                f"No session named {key!r}. Call login(name={key!r}) first."
            )
        return session

    def rename_session(self, old_name: str, new_name: str) -> None:
        """Rename a session, moving its persisted files.

        Args:
            old_name: Current session name (use ``"default"`` for the
                default session).
            new_name: New session name.

        Raises:
            ValueError: If *old_name* does not exist or *new_name* is
                already taken.
        """
        if old_name not in self._sessions:
            raise ValueError(f"No session named {old_name!r}")
        if new_name in self._sessions:
            raise ValueError(f"Session {new_name!r} already exists")

        session = self._sessions.pop(old_name)
        old_dir = session.token_path.parent

        # Compute new path
        new_dir = self._base_path / new_name
        new_token_path = new_dir / "token.json"

        # Move files on disk
        new_dir.mkdir(parents=True, exist_ok=True)
        for fname in ("token.json", "contexts.json"):
            src = old_dir / fname
            if src.exists():
                src.rename(new_dir / fname)
        # Clean up old directory if empty and not the base path
        if old_dir != self._base_path and old_dir.exists():
            try:
                old_dir.rmdir()
            except OSError:
                pass  # not empty, leave it

        # Update session
        session.name = new_name
        session.token_path = new_token_path
        self._sessions[new_name] = session

        # Update default session reference if needed
        if self._default_session is session:
            self._default_session = session

        logger.info("Renamed session %r -> %r", old_name, new_name)

    def logout(self, name: str | None = None) -> None:
        """Log out a session, removing its persisted credentials.

        Args:
            name: Session name. ``None`` logs out the default session.

        Raises:
            ValueError: If the session does not exist.
        """
        key = name or _DEFAULT_SESSION
        if key not in self._sessions:
            raise ValueError(f"No session named {key!r}")

        session = self._sessions.pop(key)
        session_dir = session.token_path.parent

        # Remove persisted files
        for fname in ("token.json", "contexts.json"):
            f = session_dir / fname
            if f.exists():
                f.unlink()

        # Remove directory if empty and not the base path
        if session_dir != self._base_path and session_dir.exists():
            try:
                session_dir.rmdir()
            except OSError:
                pass

        logger.info(
            "Logged out session %r (bot_id=%s)",
            key,
            session.bot_info.bot_id if session.bot_info else None,
        )

    def _find_session_for_user(self, user_id: str) -> _Session | None:
        """Find the session with the most recent context_token for a user."""
        best: _Session | None = None
        best_ts = 0.0
        for s in self._sessions.values():
            if user_id in s.context_tokens:
                ts = s.context_timestamps.get(user_id, 0.0)
                if ts > best_ts:
                    best = s
                    best_ts = ts
        return best

    # ------------------------------------------------------------------
    # Persistence helpers (per-session)
    # ------------------------------------------------------------------

    @staticmethod
    def _load_session_state(session: _Session) -> None:
        """Load persisted bot credentials and cursor for a session."""
        if not session.token_path.exists():
            return
        try:
            data = json.loads(session.token_path.read_text())
            session.bot_info = BotInfo(
                bot_id=data["bot_id"],
                base_url=data["base_url"],
                token=data["token"],
            )
            session.cursor = data.get("cursor", "")
            logger.info(
                "Loaded credentials for %s (session=%s)",
                session.bot_info.bot_id,
                session.name,
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load state from %s: %s", session.token_path, e)

    @staticmethod
    def _save_session_state(session: _Session) -> None:
        """Persist bot credentials and cursor for a session."""
        if not session.bot_info:
            return
        session.token_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "bot_id": session.bot_info.bot_id,
            "base_url": session.bot_info.base_url,
            "token": session.bot_info.token,
            "cursor": session.cursor,
        }
        session.token_path.write_text(json.dumps(data, indent=2))

    @staticmethod
    def _load_session_contexts(session: _Session) -> None:
        """Load persisted context tokens for a session."""
        if not session.contexts_path.exists():
            return
        try:
            data = json.loads(session.contexts_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "Failed to load contexts from %s: %s", session.contexts_path, e
            )
            return

        now = time.time()
        expiry = 24 * 3600
        for user_id, entry in data.items():
            if not isinstance(entry, dict):
                continue
            token = entry.get("t", "")
            ts = entry.get("ts", 0.0)
            if token and (now - ts) < expiry:
                session.context_tokens[user_id] = token
                session.context_timestamps[user_id] = ts

        logger.debug(
            "Loaded %d context token(s) from %s",
            len(session.context_tokens),
            session.contexts_path,
        )

    @staticmethod
    def _save_session_contexts(session: _Session) -> None:
        """Persist context tokens for a session."""
        session.token_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            user_id: {"t": token, "ts": session.context_timestamps.get(user_id, 0.0)}
            for user_id, token in session.context_tokens.items()
        }
        session.contexts_path.write_text(json.dumps(data, indent=2))

    # ------------------------------------------------------------------
    # Backward-compatible delegation
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Load state for the default session (backward compat)."""
        self._load_session_state(self._default_session)

    def _save_state(self) -> None:
        """Save state for the default session (backward compat)."""
        self._save_session_state(self._default_session)

    def _load_contexts(self) -> None:
        """Load contexts for the default session (backward compat)."""
        self._load_session_contexts(self._default_session)

    def _save_contexts(self) -> None:
        """Save contexts for the default session (backward compat)."""
        self._save_session_contexts(self._default_session)

    # Backward-compatible attribute access for tests that poke internals
    @property
    def _bot_info(self) -> BotInfo | None:
        return self._default_session.bot_info

    @_bot_info.setter
    def _bot_info(self, value: BotInfo | None) -> None:
        self._default_session.bot_info = value

    @property
    def _cursor(self) -> str:
        return self._default_session.cursor

    @_cursor.setter
    def _cursor(self, value: str) -> None:
        self._default_session.cursor = value

    @property
    def _context_tokens(self) -> dict[str, str]:
        return self._default_session.context_tokens

    @_context_tokens.setter
    def _context_tokens(self, value: dict[str, str]) -> None:
        self._default_session.context_tokens = value

    @property
    def _context_timestamps(self) -> dict[str, float]:
        return self._default_session.context_timestamps

    @_context_timestamps.setter
    def _context_timestamps(self, value: dict[str, float]) -> None:
        self._default_session.context_timestamps = value

    @property
    def _typing_tickets(self) -> dict[str, str]:
        return self._default_session.typing_tickets

    @_typing_tickets.setter
    def _typing_tickets(self, value: dict[str, str]) -> None:
        self._default_session.typing_tickets = value

    @property
    def _token_path(self) -> Path:
        return self._default_session.token_path

    @property
    def _contexts_path(self) -> Path:
        return self._default_session.contexts_path

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Whether any session has valid credentials."""
        return any(s.bot_info is not None for s in self._sessions.values())

    @property
    def bot_id(self) -> str | None:
        """Default session's bot identifier, or None if not logged in."""
        bi = self._default_session.bot_info
        return bi.bot_id if bi else None

    @property
    def bot_ids(self) -> dict[str, str]:
        """Map of session name to bot_id for all connected sessions."""
        return {
            name: s.bot_info.bot_id for name, s in self._sessions.items() if s.bot_info
        }

    @property
    def sessions(self) -> list[str]:
        """List of all session names."""
        return list(self._sessions.keys())

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self, name: str | None = None, force: bool = False) -> BotInfo:
        """Login via QR code scan.

        If valid credentials exist on disk and force is False, reuses them.

        Args:
            name: Session name. ``None`` uses the default session.
                A new named session stores credentials at
                ``<base_path>/<name>/token.json``.
            force: Force a new QR code login even if credentials exist.

        Returns:
            BotInfo with bot_id, base_url, and token.
        """
        if name is None:
            session = self._default_session
        elif name in self._sessions:
            session = self._sessions[name]
        else:
            token_path = self._base_path / name / "token.json"
            session = self._create_session(name, token_path)

        if session.bot_info and not force:
            logger.info(
                "Already logged in as %s (session=%s, use force=True to re-login)",
                session.bot_info.bot_id,
                session.name,
            )
            return session.bot_info

        # Step 1: Get QR code
        qr_resp = proto.get_qr_code()
        qrcode = qr_resp["qrcode"]
        qr_url = qr_resp.get("qrcode_img_content", "")

        if name:
            print(f"[Session: {name}]")
        self._display_qr(qr_url)

        # Step 2: Poll for scan confirmation (5 min deadline)
        deadline = time.monotonic() + 300
        print("Waiting for scan...", end="", flush=True)
        while time.monotonic() < deadline:
            try:
                status_resp = proto.poll_qr_status(qrcode)
            except (proto.ILinkError, TimeoutError, OSError):
                print(".", end="", flush=True)
                continue

            status = status_resp.get("status", "")

            if status == "confirmed":
                bot_token = status_resp.get("bot_token", "")
                base_url = status_resp.get("baseurl", proto.BASE_URL)
                bot_id = status_resp.get("ilink_bot_id", "")

                session.bot_info = BotInfo(
                    bot_id=bot_id,
                    base_url=base_url,
                    token=bot_token,
                )
                session.cursor = ""
                self._save_session_state(session)
                print(f"\nLogin successful! Bot ID: {bot_id}")
                return session.bot_info

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

            print(".", end="", flush=True)

        raise proto.ILinkError(ret=-1, errmsg="QR code login timed out (5 min)")

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    def recv(self, timeout: float = 35.0) -> list[Message]:
        """Receive pending messages via long-polling.

        When multiple sessions are active, polls all sessions concurrently
        and merges results.  Each returned ``Message`` has ``bot_id``
        populated so the caller knows which session received it.

        Args:
            timeout: Maximum wait time in seconds.

        Returns:
            List of received messages (may be empty on timeout).

        Raises:
            RuntimeError: If not logged in.
            SessionExpiredError: If session has expired (re-login needed).
        """
        active = [s for s in self._sessions.values() if s.bot_info]
        if not active:
            raise RuntimeError("Not logged in. Call login() first.")

        if len(active) == 1:
            return self._recv_session(active[0], timeout)

        # Parallel poll — return as soon as any session has messages,
        # cancel remaining polls to avoid blocking.
        pool = ThreadPoolExecutor(max_workers=len(active))
        futures = {pool.submit(self._recv_session, s, timeout): s for s in active}
        messages: list[Message] = []

        try:
            for f in as_completed(futures, timeout=timeout + 5):
                try:
                    result = f.result()
                except Exception as e:
                    session = futures[f]
                    logger.error("recv error for session %s: %s", session.name, e)
                    continue
                messages.extend(result)
                if messages:
                    # Got messages — cancel remaining futures and return early
                    for remaining in futures:
                        remaining.cancel()
                    break
        except TimeoutError:
            pass
        finally:
            pool.shutdown(wait=False)

        return messages

    def _recv_session(self, session: _Session, timeout: float) -> list[Message]:
        """Long-poll a single session for messages."""
        assert session.bot_info is not None

        resp = proto.get_updates(
            cursor=session.cursor,
            token=session.bot_info.token,
            base_url=session.bot_info.base_url,
        )

        new_cursor = resp.get("get_updates_buf", "")
        if new_cursor:
            session.cursor = new_cursor
            self._save_session_state(session)

        context_changed = False
        messages: list[Message] = []
        for raw_msg in resp.get("msgs", []):
            if raw_msg.get("message_type") != 1:
                continue

            msg = self._parse_message(raw_msg, bot_id=session.bot_info.bot_id)
            if msg:
                if msg.context_token:
                    session.context_tokens[msg.from_user] = msg.context_token
                    session.context_timestamps[msg.from_user] = time.time()
                    context_changed = True
                messages.append(msg)

        if context_changed:
            self._save_session_contexts(session)

        return messages

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    _UPLOAD_TO_SEND: dict[UploadMediaType, SendMediaType] = {
        UploadMediaType.IMAGE: SendMediaType.IMAGE,
        UploadMediaType.VOICE: SendMediaType.VOICE,
        UploadMediaType.FILE: SendMediaType.FILE,
        UploadMediaType.VIDEO: SendMediaType.VIDEO,
    }

    _SEND_ITEM_KEY: dict[SendMediaType, str] = {
        SendMediaType.IMAGE: "image_item",
        SendMediaType.VOICE: "voice_item",
        SendMediaType.FILE: "file_item",
        SendMediaType.VIDEO: "video_item",
    }

    def send(
        self,
        to: str,
        text: str | None = None,
        *,
        image: bytes | UploadedMedia | list[bytes | UploadedMedia] | None = None,
        voice: bytes | UploadedMedia | list[bytes | UploadedMedia] | None = None,
        file: bytes | UploadedMedia | list[bytes | UploadedMedia] | None = None,
        file_name: str | list[str] = "",
        video: bytes | UploadedMedia | list[bytes | UploadedMedia] | None = None,
    ) -> bool:
        """Send a message to a user.

        Automatically routes to the session that has a context_token for
        the target user.  If multiple sessions have a token, the one with
        the most recent timestamp is used.

        Args:
            to: Target user ID (xxx@im.wechat).
            text: Text message content.
            image: Image bytes/UploadedMedia, or list thereof.
            voice: Voice bytes/UploadedMedia, or list thereof.
            file: File bytes/UploadedMedia, or list thereof.
            file_name: File name(s). Required when sending file(s)
                as raw bytes. Ignored for UploadedMedia.
            video: Video bytes/UploadedMedia, or list thereof.

        Returns:
            True if all sends succeeded, False otherwise.

        Raises:
            RuntimeError: If not logged in.
            ValueError: If file bytes are provided without file_name,
                or if file and file_name list lengths don't match.
        """

        def _to_list(
            v: bytes | UploadedMedia | list[bytes | UploadedMedia] | None,
        ) -> list[bytes | UploadedMedia]:
            if v is None:
                return []
            if isinstance(v, (bytes, UploadedMedia)):
                return [v]
            return list(v)

        images = _to_list(image)
        voices = _to_list(voice)
        videos = _to_list(video)
        files = _to_list(file)

        # Resolve file names for raw bytes files
        fnames: list[str] = []
        if files:
            raw_files = [f for f in files if isinstance(f, bytes)]
            if raw_files:
                if isinstance(file_name, str):
                    fnames = [file_name] if file_name else []
                else:
                    fnames = list(file_name)
                if len(fnames) == 1 and len(raw_files) > 1:
                    fnames = fnames * len(raw_files)
                if len(raw_files) != len(fnames):
                    raise ValueError(
                        f"file and file_name length mismatch: "
                        f"{len(raw_files)} raw bytes vs {len(fnames)} names"
                    )
                if any(not fn for fn in fnames):
                    raise ValueError("file_name is required when sending a file")

        # Find the right session
        session = self._find_session_for_user(to)
        if session is None or session.bot_info is None:
            # Check if any session is connected
            active = [s for s in self._sessions.values() if s.bot_info]
            if not active:
                raise RuntimeError("Not logged in. Call login() first.")
            logger.warning("No context_token for user %s, cannot send", to)
            return False

        ctx_token = session.context_tokens.get(to)
        if not ctx_token:
            logger.warning("No context_token for user %s, cannot send", to)
            return False

        all_ok = True

        # Send text
        if text:
            try:
                resp = proto.send_message(
                    to_user=to,
                    text=text,
                    context_token=ctx_token,
                    token=session.bot_info.token,
                    base_url=session.bot_info.base_url,
                )
                ret = resp.get("ret", 0)
                if ret != 0:
                    logger.warning(
                        "send text to %s returned ret=%s: %s",
                        to,
                        ret,
                        resp.get("errmsg", ""),
                    )
                    all_ok = False
            except proto.ILinkError as e:
                logger.error("Failed to send text to %s: %s", to, e)
                all_ok = False

        # Build ordered send queue
        send_queue: list[tuple[bytes | UploadedMedia, UploadMediaType, str, str]] = []
        for item in images:
            send_queue.append((item, UploadMediaType.IMAGE, "image_item", ""))
        for item in voices:
            send_queue.append((item, UploadMediaType.VOICE, "voice_item", ""))

        fname_iter = (
            iter(fnames)
            if files and any(isinstance(f, bytes) for f in files)
            else iter([])
        )
        for item in files:
            if isinstance(item, UploadedMedia):
                send_queue.append(
                    (item, UploadMediaType.FILE, "file_item", item.file_name)
                )
            else:
                send_queue.append(
                    (item, UploadMediaType.FILE, "file_item", next(fname_iter))
                )

        for item in videos:
            send_queue.append((item, UploadMediaType.VIDEO, "video_item", ""))

        for item, media_type, item_key, fname in send_queue:
            if isinstance(item, UploadedMedia):
                ok = self._send_uploaded(to, item, session=session)
            else:
                ok = self._send_media(
                    to, item, media_type, item_key, file_name=fname, session=session
                )
            if not ok:
                all_ok = False

        if not text and not send_queue:
            logger.warning("send() called with no content")
            return False

        return all_ok

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Download / Upload
    # ------------------------------------------------------------------

    def download(self, msg: Message) -> bytes:
        """Download media from a received message.

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

    def upload(
        self,
        to: str,
        data: bytes,
        media_type: str,
        file_name: str = "",
    ) -> UploadedMedia:
        """Pre-upload media to CDN without sending.

        Returns an ``UploadedMedia`` reference that can be passed to
        ``send()`` one or more times, avoiding repeated uploads of the
        same file.

        Args:
            to: Target user ID (xxx@im.wechat). CDN uploads are
                user-bound.
            data: Raw file bytes.
            media_type: One of ``"image"``, ``"voice"``, ``"file"``,
                ``"video"``.
            file_name: Original file name (required for ``"file"`` type).

        Returns:
            UploadedMedia with CDN reference info.

        Raises:
            RuntimeError: If not logged in.
            ValueError: If media_type is invalid or file_name missing
                for file uploads.
        """
        type_map = {
            "image": UploadMediaType.IMAGE,
            "voice": UploadMediaType.VOICE,
            "file": UploadMediaType.FILE,
            "video": UploadMediaType.VIDEO,
        }
        upload_type = type_map.get(media_type)
        if upload_type is None:
            raise ValueError(
                f"Invalid media_type {media_type!r}, "
                f"expected one of {list(type_map.keys())}"
            )
        if media_type == "file" and not file_name:
            raise ValueError("file_name is required for file uploads")

        from weilink._cdn import upload_media

        # Find session for this user, or use any connected session
        session = self._find_session_for_user(to)
        if session is None or session.bot_info is None:
            active = [s for s in self._sessions.values() if s.bot_info]
            if not active:
                raise RuntimeError("Not logged in. Call login() first.")
            session = active[0]

        assert session.bot_info is not None

        def _get_url(**kwargs: Any) -> dict[str, Any]:
            assert session.bot_info is not None
            return proto.get_upload_url(
                **kwargs,
                token=session.bot_info.token,
                base_url=session.bot_info.base_url,
            )

        uploaded = upload_media(data, upload_type.value, to, _get_url)
        if file_name:
            uploaded = UploadedMedia(
                media_type=uploaded.media_type,
                filekey=uploaded.filekey,
                download_param=uploaded.download_param,
                aes_key_hex=uploaded.aes_key_hex,
                file_size=uploaded.file_size,
                cipher_size=uploaded.cipher_size,
                file_name=file_name,
            )
        return uploaded

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Save state for all sessions and clean up."""
        for session in self._sessions.values():
            self._save_session_state(session)

    def __enter__(self) -> WeiLink:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
        """Raise if no session is logged in."""
        if not any(s.bot_info for s in self._sessions.values()):
            raise RuntimeError("Not logged in. Call login() first.")

    def _parse_message(
        self, raw: dict[str, Any], bot_id: str | None = None
    ) -> Message | None:
        """Parse a raw iLink message dict into a Message."""
        from_user = raw.get("from_user_id", "")
        if not from_user:
            return None

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
            bot_id=bot_id,
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

    def _send_uploaded(
        self,
        to: str,
        uploaded: UploadedMedia,
        session: _Session | None = None,
    ) -> bool:
        """Send a pre-uploaded media reference without re-uploading.

        Args:
            to: Target user ID.
            uploaded: UploadedMedia from upload().
            session: Session to use. Auto-detected if None.

        Returns:
            True if sent successfully.
        """
        if session is None:
            session = self._find_session_for_user(to)
        if session is None or session.bot_info is None:
            logger.warning("No session/context_token for user %s, cannot send", to)
            return False

        ctx_token = session.context_tokens.get(to)
        if not ctx_token:
            logger.warning("No context_token for user %s, cannot send", to)
            return False

        send_type = self._UPLOAD_TO_SEND[uploaded.media_type]
        item_key = self._SEND_ITEM_KEY[send_type]

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
        if uploaded.file_name and item_key == "file_item":
            media_dict["file_name"] = uploaded.file_name
            media_dict["len"] = str(uploaded.file_size)

        item_list = [{"type": send_type.value, item_key: media_dict}]

        try:
            resp = proto.send_media_message(
                to_user=to,
                item_list=item_list,
                context_token=ctx_token,
                token=session.bot_info.token,
                base_url=session.bot_info.base_url,
            )
            ret = resp.get("ret", 0)
            if ret != 0:
                logger.warning(
                    "send uploaded media to %s returned ret=%s: %s",
                    to,
                    ret,
                    resp.get("errmsg", ""),
                )
                return False
            return True
        except proto.ILinkError as e:
            logger.error("Failed to send uploaded media to %s: %s", to, e)
            return False

    def _send_media(
        self,
        to: str,
        file_data: bytes,
        media_type: UploadMediaType,
        item_key: str,
        file_name: str | None = None,
        session: _Session | None = None,
    ) -> bool:
        """Upload and send a media message.

        Args:
            to: Target user ID.
            file_data: Raw file bytes.
            media_type: Upload media type enum value.
            item_key: Item key in message body (e.g. "image_item").
            file_name: Original file name (for file_item only).
            session: Session to use. Auto-detected if None.

        Returns:
            True if sent successfully.
        """
        from weilink._cdn import upload_media

        if session is None:
            session = self._find_session_for_user(to)
        if session is None or session.bot_info is None:
            logger.warning("No session/context_token for user %s, cannot send", to)
            return False

        ctx_token = session.context_tokens.get(to)
        if not ctx_token:
            logger.warning("No context_token for user %s, cannot send", to)
            return False

        def _get_url(**kwargs: Any) -> dict[str, Any]:
            assert session.bot_info is not None
            return proto.get_upload_url(
                **kwargs,
                token=session.bot_info.token,
                base_url=session.bot_info.base_url,
            )

        try:
            uploaded = upload_media(file_data, media_type.value, to, _get_url)

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
                token=session.bot_info.token,
                base_url=session.bot_info.base_url,
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
        session = self._find_session_for_user(to)
        if session is None or session.bot_info is None:
            self._ensure_connected()
            # Fall back to default session
            session = self._default_session
            if session.bot_info is None:
                return

        ticket = session.typing_tickets.get(to)
        if not ticket:
            ctx_token = session.context_tokens.get(to)
            try:
                config = proto.get_config(
                    user_id=to,
                    token=session.bot_info.token,
                    context_token=ctx_token,
                    base_url=session.bot_info.base_url,
                )
                ticket = config.get("typing_ticket", "")
                if ticket:
                    session.typing_tickets[to] = ticket
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
                token=session.bot_info.token,
                base_url=session.bot_info.base_url,
            )
        except proto.ILinkError as e:
            logger.warning("Failed to set typing for %s: %s", to, e)
