"""WeiLink client - public API for WeChat iLink Bot protocol."""

from __future__ import annotations

import base64
import json
import logging
import os
import queue
import signal
import threading
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Callable

from weilink.filelock import FileLock
from weilink import _protocol as proto
from weilink.models import (
    BotInfo,
    FileInfo,
    ImageInfo,
    MediaContent,
    MediaInfo,
    Message,
    MessageType,
    RefMessage,
    SendMediaType,
    SendResult,
    UploadMediaType,
    UploadedMedia,
    VideoInfo,
    VoiceInfo,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_PATH = Path.home() / ".weilink"
_DEFAULT_SESSION = "default"
_FALLBACK_WINDOW = 60  # seconds: time window for Route C degraded SQLite reads


def _atomic_write(path: Path, data: str) -> None:
    """Write *data* to *path* atomically via a temp file + rename."""
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(data)
    os.replace(tmp, path)


@dataclass
class _Session:
    """Per-session state for a single bot registration."""

    name: str
    token_path: Path
    bot_info: BotInfo | None = None
    cursor: str = ""
    context_tokens: dict[str, str] = field(default_factory=dict)
    context_timestamps: dict[str, float] = field(default_factory=dict)
    send_timestamps: dict[str, float] = field(default_factory=dict)
    send_counts: dict[str, int] = field(default_factory=dict)
    user_first_seen: dict[str, float] = field(default_factory=dict)
    typing_tickets: dict[str, str] = field(default_factory=dict)
    created_at: float | None = None
    longpoll_timeout: float | None = None
    consecutive_failures: int = 0
    _io_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def contexts_path(self) -> Path:
        """Path to the contexts persistence file (sibling to token.json)."""
        return self.token_path.parent / "contexts.json"


class Session:
    """Public handle for a WeiLink session.

    Obtained via ``wl.sessions["name"]``.  Provides read-only properties
    and management methods (rename, set_default, login, logout).

    Example::

        wl = WeiLink()
        for name in wl.sessions:
            print(name)

        s = wl.sessions["zb"]
        s.set_default()
        s.rename("new_name")
    """

    def __init__(self, client: WeiLink, internal: _Session) -> None:
        self._client = client
        self._internal = internal

    @property
    def name(self) -> str:
        """Session name."""
        return self._internal.name

    @property
    def bot_id(self) -> str | None:
        """Bot identifier, or ``None`` if not logged in."""
        bi = self._internal.bot_info
        return bi.bot_id if bi else None

    @property
    def user_id(self) -> str | None:
        """WeChat user ID that authorized the bot, or ``None``."""
        bi = self._internal.bot_info
        return bi.user_id if bi else None

    @property
    def is_connected(self) -> bool:
        """Whether this session has valid credentials."""
        return self._internal.bot_info is not None

    @property
    def is_default(self) -> bool:
        """Whether this session is the current default."""
        return self._internal is self._client._default_session

    @property
    def created_at(self) -> float | None:
        """Epoch timestamp when this session was first saved, or ``None``."""
        return self._internal.created_at

    def rename(self, new_name: str) -> None:
        """Rename this session.

        Args:
            new_name: New session name.

        Raises:
            ValueError: If *new_name* is already taken or is ``"default"``.
        """
        self._client.rename_session(self._internal.name, new_name)

    def set_default(self) -> None:
        """Set this session as the default.

        The default session is used when API methods are called without
        a session name (e.g. ``login()``, ``send()``).
        """
        self._client.set_default(self._internal.name)

    def login(self, force: bool = False) -> BotInfo:
        """Login a session via QR code scan.

        Args:
            force: Force a new QR code login even if credentials exist.

        Returns:
            BotInfo with bot_id, base_url, and token.
        """
        return self._client.login(name=self._internal.name, force=force)

    def logout(self) -> None:
        """Logout this session, removing persisted credentials."""
        self._client.logout(self._internal.name)

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        default = ", default" if self.is_default else ""
        return f"Session({self.name!r}, {status}{default})"


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
        message_store: bool | str | Path | None = None,
    ):
        """Initialize the WeiLink client.

        Args:
            token_path: Path to persist bot credentials for the default
                session.  Defaults to ``~/.weilink/token.json``.
            base_path: Base directory for multi-session storage.  Named
                sessions are stored under ``<base_path>/<name>/``.
                Defaults to ``~/.weilink/``.  Ignored if *token_path*
                is given (the base path is derived from it).
            message_store: Enable SQLite message persistence.
                ``None`` (default) disables it.  ``True`` uses
                ``<base_path>/messages.db``.  A path string or
                ``Path`` specifies a custom database location.
        """
        if token_path is not None:
            self._base_path = Path(token_path).parent
        elif base_path is not None:
            self._base_path = Path(base_path)
        else:
            self._base_path = _DEFAULT_BASE_PATH

        # Auto-migrate legacy flat default layout into default/ subdir.
        if token_path is None:
            self._migrate_flat_default()

        default_token = (
            Path(token_path)
            if token_path
            else self._base_path / _DEFAULT_SESSION / "token.json"
        )

        self._sessions: dict[str, _Session] = {}
        self._admin_server: Any = None
        self._message_handlers: list[Callable[[Message], None]] = []
        self._message_queue: queue.Queue[Message] = queue.Queue(maxsize=1000)
        self._dispatcher_thread: threading.Thread | None = None
        self._dispatcher_stop = threading.Event()

        # Cross-process file locks
        self._poll_lock = FileLock(self._base_path / ".poll.lock")
        self._data_lock = FileLock(self._base_path / ".data.lock")

        # Optional SQLite message persistence
        self._message_store: Any = None
        if message_store is not None and message_store is not False:
            from weilink._store import MessageStore

            if message_store is True:
                db_path = self._base_path / "messages.db"
            else:
                db_path = Path(str(message_store))
            self._message_store = MessageStore(db_path)

        # Auto-discover sessions from subdirectories (including "default")
        discovered: list[_Session] = []
        if self._base_path.is_dir():
            for child in sorted(self._base_path.iterdir()):
                if child.is_dir() and (child / "token.json").exists():
                    name = child.name
                    if name not in self._sessions:
                        discovered.append(
                            self._create_session(name, child / "token.json")
                        )

        # Determine which session is the default.
        if _DEFAULT_SESSION in self._sessions:
            # "default" was discovered on disk.
            self._default_session = self._sessions[_DEFAULT_SESSION]
        elif default_token.exists():
            # Explicit token_path outside base_path scan — create it.
            self._default_session = self._create_session(
                _DEFAULT_SESSION, default_token
            )
        elif not discovered:
            # First use — create a placeholder (no file on disk yet).
            self._default_session = self._create_session(
                _DEFAULT_SESSION, default_token
            )
        else:
            # Named sessions exist but no "default" — pick one.
            saved_default = self._load_default_session_name()
            if saved_default and saved_default in self._sessions:
                self._default_session = self._sessions[saved_default]
            else:
                connected = [s for s in discovered if s.bot_info]
                if connected:
                    connected.sort(key=lambda s: s.created_at or float("inf"))
                    self._default_session = connected[0]
                else:
                    self._default_session = discovered[0]

    # ------------------------------------------------------------------
    # Legacy layout migration
    # ------------------------------------------------------------------

    def _migrate_flat_default(self) -> None:
        """Move legacy flat ``token.json``/``contexts.json`` into ``default/``.

        Early single-session versions stored credentials directly under
        ``base_path/``.  This migrates them into ``base_path/default/`` so
        that every session uses the same subdirectory layout.
        """
        flat_token = self._base_path / "token.json"
        dest_dir = self._base_path / _DEFAULT_SESSION
        dest_token = dest_dir / "token.json"

        if not flat_token.exists() or dest_token.exists():
            return

        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            flat_token.rename(dest_token)
        except FileNotFoundError:
            # Another process migrated first — harmless.
            return

        flat_ctx = self._base_path / "contexts.json"
        if flat_ctx.exists():
            try:
                flat_ctx.rename(dest_dir / "contexts.json")
            except FileNotFoundError:
                pass

        logger.info("Migrated legacy flat default session into %s/", _DEFAULT_SESSION)

    # ------------------------------------------------------------------
    # Default session persistence
    # ------------------------------------------------------------------

    _DEFAULT_SESSION_FILE = ".default_session"

    def _load_default_session_name(self) -> str | None:
        """Load the persisted default session name from disk."""
        p = self._base_path / self._DEFAULT_SESSION_FILE
        if not p.exists():
            return None
        try:
            return p.read_text().strip() or None
        except OSError:
            return None

    def _save_default_session_name(self) -> None:
        """Persist the current default session name to disk."""
        self._base_path.mkdir(parents=True, exist_ok=True)
        p = self._base_path / self._DEFAULT_SESSION_FILE
        _atomic_write(p, self._default_session.name)

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
        if name is None:
            return self._default_session
        session = self._sessions.get(name)
        if session is None:
            raise ValueError(
                f"No session named {name!r}. Call login(name={name!r}) first."
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
        if new_name == _DEFAULT_SESSION:
            raise ValueError(
                f"Cannot rename to {_DEFAULT_SESSION!r}. "
                "Use set_default() to change which session is the default."
            )
        if new_name in self._sessions:
            raise ValueError(f"Session {new_name!r} already exists")

        session = self._sessions.pop(old_name)

        # Hold both the cross-process data lock and the in-process I/O
        # lock so no other process or thread can read/write the old path
        # while we move files and update token_path.
        with self._data_lock, session._io_lock:
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

            # Update session paths before releasing lock, so any waiting
            # writer will use the new path.
            session.name = new_name
            session.token_path = new_token_path

            # Force-remove old directory (shutil.rmtree handles non-empty)
            if old_dir != self._base_path and old_dir.exists():
                import shutil

                shutil.rmtree(old_dir, ignore_errors=True)

        self._sessions[new_name] = session

        # Update default session persistence if this was the default
        if self._default_session is session:
            self._save_default_session_name()

        logger.info("Renamed session %r -> %r", old_name, new_name)

    def logout(self, name: str | None = None) -> None:
        """Log out a session, removing its persisted credentials.

        Args:
            name: Session name. ``None`` logs out the default session.

        Raises:
            ValueError: If the session does not exist.
        """
        if name is None:
            key = self._default_session.name
        else:
            key = name
        if key not in self._sessions:
            raise ValueError(f"No session named {key!r}")

        session = self._sessions.pop(key)
        with self._data_lock, session._io_lock:
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
        with session._io_lock:
            if not session.token_path.exists():
                return
            try:
                data = json.loads(session.token_path.read_text())
                session.bot_info = BotInfo(
                    bot_id=data["bot_id"],
                    base_url=data["base_url"],
                    token=data["token"],
                    user_id=data.get("user_id", ""),
                )
                session.cursor = data.get("cursor", "")
                session.created_at = data.get("created_at")
                if session.created_at is None:
                    # Legacy token without created_at: fall back to file mtime
                    try:
                        session.created_at = session.token_path.stat().st_mtime
                    except OSError:
                        pass
                logger.debug(
                    "Loaded credentials for %s (session=%s)",
                    session.bot_info.bot_id,
                    session.name,
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(
                    "Failed to load state from %s: %s", session.token_path, e
                )

    @staticmethod
    def _save_session_state(session: _Session) -> None:
        """Persist bot credentials and cursor for a session."""
        if not session.bot_info:
            return
        if session.created_at is None:
            session.created_at = time.time()
        with session._io_lock:
            session.token_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "bot_id": session.bot_info.bot_id,
                "base_url": session.bot_info.base_url,
                "token": session.bot_info.token,
                "user_id": session.bot_info.user_id,
                "cursor": session.cursor,
                "created_at": session.created_at,
            }
            _atomic_write(session.token_path, json.dumps(data, indent=2))

    @staticmethod
    def _load_session_contexts(session: _Session) -> None:
        """Load persisted context tokens for a session."""
        with session._io_lock:
            if not session.contexts_path.exists():
                return
            try:
                data = json.loads(session.contexts_path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    "Failed to load contexts from %s: %s",
                    session.contexts_path,
                    e,
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
            # Load send_counts, send_timestamps and user_first_seen
            sc = entry.get("sc", 0)
            if sc and token and (now - ts) < expiry:
                session.send_counts[user_id] = sc
            send_ts = entry.get("send_ts", 0.0)
            if send_ts:
                session.send_timestamps[user_id] = send_ts
            first_seen = entry.get("first_seen", 0.0)
            if first_seen:
                session.user_first_seen[user_id] = first_seen
            elif ts:
                # Legacy fallback: use earliest known interaction time
                session.user_first_seen[user_id] = ts

        logger.debug(
            "Loaded %d context token(s) from %s",
            len(session.context_tokens),
            session.contexts_path,
        )

    @staticmethod
    def _save_session_contexts(session: _Session) -> None:
        """Persist context tokens for a session."""
        # Collect all known user IDs across tokens and timestamps
        all_users = (
            set(session.context_tokens)
            | set(session.send_timestamps)
            | set(session.send_counts)
            | set(session.user_first_seen)
        )
        data = {}
        for user_id in all_users:
            entry: dict[str, Any] = {}
            if user_id in session.context_tokens:
                entry["t"] = session.context_tokens[user_id]
                entry["ts"] = session.context_timestamps.get(user_id, 0.0)
            if user_id in session.send_timestamps:
                entry["send_ts"] = session.send_timestamps[user_id]
            if session.send_counts.get(user_id, 0):
                entry["sc"] = session.send_counts[user_id]
            if user_id in session.user_first_seen:
                entry["first_seen"] = session.user_first_seen[user_id]
            if entry:
                data[user_id] = entry
        with session._io_lock:
            session.token_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(session.contexts_path, json.dumps(data, indent=2))

    @staticmethod
    def _merge_contexts_from_disk(session: _Session, updated_users: set[str]) -> None:
        """Re-read contexts from disk and merge with in-memory state.

        For users in *updated_users* the in-memory state (new token from
        recv) is authoritative.  For all other users the disk state is
        authoritative (preserves send_counts from other processes).

        Must be called with the data lock held.
        """
        if not session.contexts_path.exists():
            return
        try:
            disk_data = json.loads(session.contexts_path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        now = time.time()
        expiry = 24 * 3600
        for user_id, entry in disk_data.items():
            if user_id in updated_users:
                # In-memory state is newer (just received fresh token)
                continue
            if not isinstance(entry, dict):
                continue
            token = entry.get("t", "")
            ts = entry.get("ts", 0.0)
            if token and (now - ts) < expiry:
                session.context_tokens[user_id] = token
                session.context_timestamps[user_id] = ts
            sc = entry.get("sc", 0)
            if sc and token and (now - ts) < expiry:
                session.send_counts[user_id] = sc
            send_ts = entry.get("send_ts", 0.0)
            if send_ts:
                session.send_timestamps[user_id] = send_ts
            first_seen = entry.get("first_seen", 0.0)
            if first_seen:
                session.user_first_seen[user_id] = first_seen

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
    def sessions(self) -> dict[str, Session]:
        """All sessions as a name -> Session mapping.

        Iterating yields session names (strings)::

            for name in wl.sessions: ...
            list(wl.sessions)  # ["default", "zb"]

        Dict-like access for Session objects::

            wl.sessions["zb"].rename("new_name")
            wl.sessions["zb"].set_default()
        """
        return {name: Session(self, s) for name, s in self._sessions.items()}

    def set_default(self, name: str) -> None:
        """Set a named session as the default session.

        The default session is used when API methods are called without
        a session name (e.g. ``login()``, ``send()``).

        Args:
            name: Session name to set as default.

        Raises:
            ValueError: If the session does not exist.
        """
        if name not in self._sessions:
            raise ValueError(f"No session named {name!r}")
        self._default_session = self._sessions[name]
        self._save_default_session_name()

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self, name: str | None = None, force: bool = False) -> BotInfo:
        """Login a session via QR code scan.

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
                user_id = status_resp.get("ilink_user_id", "")

                session.bot_info = BotInfo(
                    bot_id=bot_id,
                    base_url=base_url,
                    token=bot_token,
                    user_id=user_id,
                )
                session.cursor = ""
                with self._data_lock:
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

            # "wait" = server says no scan yet; any other unknown status
            # is treated the same — keep polling.
            print(".", end="", flush=True)

        raise proto.ILinkError(ret=-1, errmsg="QR code login timed out (5 min)")

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    def recv(self, timeout: float = 35.0) -> list[Message]:
        """Receive pending messages via long-polling.

        When the dispatcher is running (via :meth:`run_forever` or
        :meth:`run_background`), messages are read from an internal queue
        instead of polling iLink directly.  This avoids cursor conflicts.

        When multiple sessions are active, polls all sessions concurrently
        and merges results.  Each returned ``Message`` has ``bot_id``
        populated so the caller knows which session received it.

        Args:
            timeout: Maximum wait time in seconds.

        Returns:
            List of received messages (may be empty on timeout).

        Raises:
            RuntimeError: If not logged in (only when dispatcher is not
                running).
            SessionExpiredError: If session has expired (re-login needed).
        """
        if self._dispatcher_thread is not None and self._dispatcher_thread.is_alive():
            return self._recv_from_queue(timeout)
        return self._recv_direct(timeout)

    def _recv_from_queue(self, timeout: float) -> list[Message]:
        """Drain messages from the internal queue."""
        messages: list[Message] = []
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                msg = self._message_queue.get(timeout=min(remaining, 1.0))
                messages.append(msg)
                # Drain any immediately available messages
                while True:
                    try:
                        messages.append(self._message_queue.get_nowait())
                    except queue.Empty:
                        break
                break
            except queue.Empty:
                continue
        return messages

    def _recv_direct(self, timeout: float = 35.0) -> list[Message]:
        """Long-poll iLink directly for messages."""
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
        except (TimeoutError, FuturesTimeoutError):
            pass
        finally:
            pool.shutdown(wait=False)

        return messages

    def _recv_session(self, session: _Session, timeout: float) -> list[Message]:
        """Long-poll a single session for messages."""
        assert session.bot_info is not None

        # Cross-process: only one process may poll at a time.
        if not self._poll_lock.try_lock():
            # Route C: fall back to SQLite store when another process is polling.
            if self._message_store is not None:
                return self._recv_from_store(session)
            return []

        try:
            return self._recv_session_locked(session, timeout)
        finally:
            self._poll_lock.unlock()

    def _recv_from_store(self, session: _Session) -> list[Message]:
        """Read recent messages from SQLite when live polling is unavailable.

        This is the Route C fallback: when the poll lock is held by another
        process, read messages that the primary poller already stored.
        No cursor or context_token updates are performed.
        """
        assert session.bot_info is not None
        assert self._message_store is not None

        since_ms = int((time.time() - _FALLBACK_WINDOW) * 1000)
        messages = self._message_store.query_messages(
            bot_id=session.bot_info.bot_id,
            direction=1,
            since_ms=since_ms,
        )
        if messages:
            logger.info(
                "Route C fallback: read %d message(s) from store for session %s",
                len(messages),
                session.name,
            )
        else:
            logger.debug(
                "Route C fallback: no recent messages in store for session %s",
                session.name,
            )
        return messages

    def _recv_session_locked(self, session: _Session, timeout: float) -> list[Message]:
        """Long-poll implementation, called with poll_lock held."""
        assert session.bot_info is not None
        # Re-read disk state so we pick up cursor/context changes from
        # other processes (disk is the source of truth).
        with self._data_lock:
            self._load_session_state(session)
            self._load_session_contexts(session)

        # Backoff on consecutive failures (spec §4.4):
        # 1-2 failures: wait 2s, 3+ failures: wait 30s
        if session.consecutive_failures > 0:
            backoff = 30.0 if session.consecutive_failures >= 3 else 2.0
            logger.debug(
                "Backoff %.0fs after %d consecutive failures (session=%s)",
                backoff,
                session.consecutive_failures,
                session.name,
            )
            time.sleep(backoff)

        # Use server-provided timeout if available
        poll_timeout = session.longpoll_timeout or timeout
        try:
            resp = proto.get_updates(
                cursor=session.cursor,
                token=session.bot_info.token,
                base_url=session.bot_info.base_url,
                timeout=poll_timeout + 5,
            )
        except proto.SessionExpiredError:
            # Clear cursor and context tokens per protocol spec §9.2
            session.cursor = ""
            session.context_tokens.clear()
            session.context_timestamps.clear()
            with self._data_lock:
                self._save_session_state(session)
                self._save_session_contexts(session)
            raise
        except (TimeoutError, OSError):
            # HTTP timeout — no messages arrived within the window
            return []
        except proto.ILinkError:
            session.consecutive_failures += 1
            raise

        session.consecutive_failures = 0

        # Parse messages and collect context token updates
        users_with_new_token: set[str] = set()
        messages: list[Message] = []
        for raw_msg in resp.get("msgs", []):
            msg_type = raw_msg.get("message_type")
            logger.debug(
                "Raw message: message_type=%s, keys=%s",
                msg_type,
                list(raw_msg.keys()),
            )
            # Dump full item_list for all messages
            for i, item in enumerate(raw_msg.get("item_list", [])):
                logger.debug(
                    "  item[%d] full: %s",
                    i,
                    json.dumps(item, ensure_ascii=False, default=str),
                )
            if msg_type != 1:
                logger.debug(
                    "Skipping message_type=%s, full raw: %s",
                    msg_type,
                    json.dumps(raw_msg, ensure_ascii=False, default=str),
                )
                continue

            msg = self._parse_message(raw_msg, bot_id=session.bot_info.bot_id)
            if msg:
                # Log parsed result
                logger.debug(
                    "Parsed message: type=%s, text=%r, from=%s",
                    msg.msg_type.name,
                    msg.text[:50] if msg.text else None,
                    msg.from_user,
                )
                if msg.context_token:
                    old_token = session.context_tokens.get(msg.from_user)
                    session.context_tokens[msg.from_user] = msg.context_token
                    session.context_timestamps[msg.from_user] = time.time()
                    if msg.context_token != old_token:
                        session.send_counts[msg.from_user] = 0
                    if msg.from_user not in session.user_first_seen:
                        session.user_first_seen[msg.from_user] = time.time()
                    users_with_new_token.add(msg.from_user)
                messages.append(msg)

        # Persist received messages to SQLite (if enabled).
        if messages and self._message_store is not None:
            try:
                self._message_store.store(messages, direction=1)
            except Exception:
                logger.warning("Failed to store messages", exc_info=True)

        # Merge with disk: re-read contexts, then overwrite only users
        # that received new tokens.  This preserves send_counts updated
        # by other processes for users NOT in this batch.
        new_cursor = resp.get("get_updates_buf", "")
        with self._data_lock:
            if users_with_new_token:
                self._merge_contexts_from_disk(session, users_with_new_token)
            if new_cursor:
                session.cursor = new_cursor
            self._save_session_state(session)
            if users_with_new_token:
                self._save_session_contexts(session)

        # Update client-side timeout if server provides one
        lp_ms = resp.get("longpolling_timeout_ms")
        if lp_ms is not None and isinstance(lp_ms, (int, float)) and lp_ms > 0:
            session.longpoll_timeout = lp_ms / 1000.0

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
        image: MediaContent | None = None,
        voice: MediaContent | None = None,
        file: MediaContent | None = None,
        file_name: str | list[str] = "",
        video: MediaContent | None = None,
        auto_recv: bool = False,
    ) -> SendResult:
        """Send a message to a user.

        Automatically routes to the session that has a context_token for
        the target user.  If multiple sessions have a token, the one with
        the most recent timestamp is used.

        Each ``context_token`` allows at most 10 outbound messages (text
        or media).  The returned ``SendResult.remaining`` shows how many
        sends are left on the current token.

        Args:
            to: Target user ID (xxx@im.wechat).
            text: Text message content.  Must be <= 16 KiB UTF-8.
            image: Image bytes/UploadedMedia, or list thereof.
            voice: Voice bytes/UploadedMedia, or list thereof.
            file: File bytes/UploadedMedia, or list thereof.
            file_name: File name(s). Required when sending file(s)
                as raw bytes. Ignored for UploadedMedia.
            video: Video bytes/UploadedMedia, or list thereof.
            auto_recv: If True, call ``recv()`` with a short timeout
                before sending to refresh context tokens.  Useful when
                the caller may not have called ``recv()`` recently.

        Returns:
            A SendResult with ``success`` flag, any ``messages``
            received during auto-recv, and ``remaining`` quota count.
            Evaluates to ``True``/``False`` for backward compatibility.

        Raises:
            RuntimeError: If not logged in.
            ValueError: If file bytes are provided without file_name,
                or if file and file_name list lengths don't match.
            QuotaExhaustedError: If the 10-message quota for the
                current context_token is exhausted.
            TextTooLongError: If text exceeds 16 KiB UTF-8 bytes.
        """
        recv_messages: list[Message] = []
        if auto_recv:
            try:
                recv_messages = self.recv(timeout=1)
            except Exception:
                pass  # best-effort refresh

        def _to_list(
            v: MediaContent | None,
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

        # Text byte length check (pure validation, no lock needed)
        if text:
            text_bytes = len(text.encode("utf-8"))
            if text_bytes > proto.TEXT_BYTE_LIMIT:
                raise proto.TextTooLongError(
                    ret=-2,
                    errmsg=(
                        f"Text is {text_bytes} UTF-8 bytes, exceeds the "
                        f"{proto.TEXT_BYTE_LIMIT} byte limit. "
                        f"Truncate or split before sending."
                    ),
                )

        # Build ordered send queue (pure computation, no lock needed)
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

        if not text and not send_queue:
            logger.warning("send() called with no content")
            return SendResult(success=False, messages=recv_messages)

        # --- Core send cycle under data_lock ---
        # Re-read contexts from disk so we use the latest token and
        # send_count written by other processes.
        with self._data_lock:
            for s in self._sessions.values():
                self._load_session_contexts(s)

            session = self._find_session_for_user(to)
            if session is None or session.bot_info is None:
                active = [s for s in self._sessions.values() if s.bot_info]
                if not active:
                    raise RuntimeError("Not logged in. Call login() first.")
                logger.warning("No context_token for user %s, cannot send", to)
                return SendResult(success=False, messages=recv_messages)

            ctx_token = session.context_tokens.get(to)
            if not ctx_token:
                logger.warning("No context_token for user %s, cannot send", to)
                return SendResult(success=False, messages=recv_messages)

            # Quota check with fresh send_count from disk
            sent = session.send_counts.get(to, 0)
            remaining = proto.CONTEXT_TOKEN_QUOTA - sent
            if remaining <= 0:
                raise proto.QuotaExhaustedError(
                    ret=-2,
                    errmsg=(
                        f"Context token quota exhausted "
                        f"({proto.CONTEXT_TOKEN_QUOTA} messages sent). "
                        f"Wait for the user to send a new message."
                    ),
                )

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
                    else:
                        session.send_counts[to] = session.send_counts.get(to, 0) + 1
                except proto.ILinkError as e:
                    logger.error("Failed to send text to %s: %s", to, e)
                    all_ok = False

            for item, media_type, item_key, fname in send_queue:
                # Check quota before each media send
                if session.send_counts.get(to, 0) >= proto.CONTEXT_TOKEN_QUOTA:
                    logger.warning(
                        "Quota exhausted after %d sends, skipping remaining media",
                        session.send_counts.get(to, 0),
                    )
                    all_ok = False
                    break
                if isinstance(item, UploadedMedia):
                    ok = self._send_uploaded(to, item, session=session)
                else:
                    ok = self._send_media(
                        to,
                        item,
                        media_type,
                        item_key,
                        file_name=fname,
                        session=session,
                    )
                if ok:
                    session.send_counts[to] = session.send_counts.get(to, 0) + 1
                else:
                    all_ok = False

            if all_ok:
                session.send_timestamps[to] = time.time()
            self._save_session_contexts(session)

        # Persist sent text to SQLite (if enabled).
        if all_ok and text and self._message_store is not None:
            try:
                self._message_store.store_sent(
                    user_id=to,
                    bot_id=session.bot_info.bot_id if session.bot_info else "",
                    text=text,
                )
            except Exception:
                logger.warning("Failed to store sent message", exc_info=True)

        remaining = proto.CONTEXT_TOKEN_QUOTA - session.send_counts.get(to, 0)
        return SendResult(success=all_ok, messages=recv_messages, remaining=remaining)

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
    # Callback / dispatcher
    # ------------------------------------------------------------------

    def on_message(
        self, handler: Callable[[Message], None]
    ) -> Callable[[Message], None]:
        """Register a message handler.

        Can be used as a decorator or called directly::

            @wl.on_message
            def handle(msg):
                print(msg.text)

            # or
            wl.on_message(some_function)

        Args:
            handler: Callable that accepts a Message.

        Returns:
            The handler unchanged (for decorator usage).
        """
        self._message_handlers.append(handler)
        return handler

    def run_forever(self, poll_timeout: float = 35.0) -> None:
        """Start the dispatcher and block until :meth:`stop` is called.

        Installs SIGINT/SIGTERM handlers so ``Ctrl+C`` triggers a
        graceful shutdown.  Calls :meth:`close` before returning.

        Args:
            poll_timeout: Timeout per recv poll cycle in seconds.
        """
        self._start_dispatcher(poll_timeout)

        prev_sigint = signal.getsignal(signal.SIGINT)
        prev_sigterm = signal.getsignal(signal.SIGTERM)

        def _shutdown(signum: int, frame: Any) -> None:
            self.stop()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        try:
            self._dispatcher_stop.wait()
        finally:
            signal.signal(signal.SIGINT, prev_sigint)
            signal.signal(signal.SIGTERM, prev_sigterm)
            self.close()

    def run_background(self, poll_timeout: float = 35.0) -> None:
        """Start the dispatcher in the background without blocking.

        Messages are dispatched to registered handlers and buffered in
        an internal queue.  Call :meth:`recv` to read from the queue,
        or use :meth:`on_message` to register handlers.

        Args:
            poll_timeout: Timeout per recv poll cycle in seconds.
        """
        self._start_dispatcher(poll_timeout)

    def stop(self) -> None:
        """Stop the dispatcher if running."""
        if self._dispatcher_thread is None:
            return
        self._dispatcher_stop.set()
        self._dispatcher_thread.join(timeout=10.0)
        self._dispatcher_thread = None
        self._dispatcher_stop.clear()

    def _start_dispatcher(self, poll_timeout: float) -> None:
        """Start the background polling thread if not already running."""
        if self._dispatcher_thread is not None and self._dispatcher_thread.is_alive():
            return
        self._dispatcher_stop.clear()
        self._dispatcher_thread = threading.Thread(
            target=self._poll_loop,
            args=(poll_timeout,),
            daemon=True,
        )
        self._dispatcher_thread.start()

    def _poll_loop(self, poll_timeout: float) -> None:
        """Background loop: poll iLink and dispatch to handlers + queue."""
        while not self._dispatcher_stop.is_set():
            try:
                messages = self._recv_direct(timeout=poll_timeout)
            except proto.SessionExpiredError:
                logger.error("Session expired, dispatcher stopping")
                break
            except RuntimeError:
                # Not logged in yet — wait briefly and retry
                if self._dispatcher_stop.wait(timeout=2.0):
                    break
                continue
            except Exception:
                logger.exception("Polling error in dispatcher")
                continue

            for msg in messages:
                # Dispatch to handlers
                for handler in self._message_handlers:
                    try:
                        handler(msg)
                    except Exception:
                        logger.exception(
                            "Handler %s raised an exception",
                            getattr(handler, "__name__", handler),
                        )

                # Enqueue for recv() consumers, drop oldest on overflow
                try:
                    self._message_queue.put_nowait(msg)
                except queue.Full:
                    try:
                        self._message_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._message_queue.put_nowait(msg)

        self._dispatcher_stop.set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_admin(self, host: str = "127.0.0.1", port: int = 8080) -> Any:
        """Start the admin panel HTTP server in a background thread.

        Args:
            host: Host address to bind to.
            port: Port number.

        Returns:
            AdminInfo with host, port, url.
        """
        from weilink.admin import AdminServer

        if self._admin_server and self._admin_server.is_running():
            return self._admin_server.get_info()
        self._admin_server = AdminServer(self, host=host, port=port)
        return self._admin_server.start()

    def stop_admin(self) -> None:
        """Stop the admin panel server."""
        if self._admin_server:
            self._admin_server.stop()
            self._admin_server = None

    def close(self) -> None:
        """Save state for all sessions and clean up."""
        self.stop()
        self.stop_admin()
        if self._message_store is not None:
            self._message_store.close()
        for session in self._sessions.values():
            self._save_session_state(session)
        self._poll_lock.close()
        self._data_lock.close()

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
            else:
                logger.debug(
                    "Unhandled item_type=%s in _parse_message, full item: %s",
                    item_type,
                    json.dumps(first, ensure_ascii=False, default=str),
                )

        ref_msg: RefMessage | None = None
        if items:
            ref_raw = first.get("ref_msg")
            if ref_raw:
                ref_msg = self._parse_ref_msg(ref_raw)

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
            ref_msg=ref_msg,
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
    def _parse_ref_msg(cls, raw: dict[str, Any]) -> RefMessage | None:
        """Parse a ref_msg dict into a RefMessage."""
        item = raw.get("message_item")
        if not item:
            return None

        item_type = item.get("type", 1)
        msg_type = (
            MessageType(item_type)
            if item_type in MessageType.__members__.values()
            else MessageType.TEXT
        )

        text: str | None = None
        image: ImageInfo | None = None
        voice: VoiceInfo | None = None
        file: FileInfo | None = None
        video: VideoInfo | None = None

        if item_type == 1 and item.get("text_item"):
            text = item["text_item"].get("text")
        elif item_type == 2 and item.get("image_item"):
            image = cls._parse_image_item(item["image_item"])
        elif item_type == 3 and item.get("voice_item"):
            voice = cls._parse_voice_item(item["voice_item"])
        elif item_type == 4 and item.get("file_item"):
            file = cls._parse_file_item(item["file_item"])
        elif item_type == 5 and item.get("video_item"):
            video = cls._parse_video_item(item["video_item"])

        return RefMessage(
            msg_type=msg_type,
            text=text,
            image=image,
            voice=voice,
            file=file,
            video=video,
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
            hd_size=raw.get("hd_size", 0),
        )

    @classmethod
    def _parse_voice_item(cls, raw: dict[str, Any]) -> VoiceInfo:
        """Parse a voice_item dict into VoiceInfo."""
        media = cls._parse_media_info(raw.get("media", {}))
        return VoiceInfo(
            media=media,
            playtime=raw.get("playtime", 0),
            text=raw.get("text", ""),
            encode_type=raw.get("encode_type", 0),
            bits_per_sample=raw.get("bits_per_sample", 0),
            sample_rate=raw.get("sample_rate", 0),
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
