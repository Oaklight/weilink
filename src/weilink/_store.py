"""SQLite-backed message persistence for WeiLink.

Stores received and sent messages in a local SQLite database, enabling
history queries and preventing message loss across restarts.

Uses WAL mode for concurrent reader/writer access.  Thread-safe via an
internal write lock; cross-process safe via SQLite's own locking.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from weilink.models import (
    FileInfo,
    ImageInfo,
    MediaInfo,
    Message,
    MessageType,
    RefMessage,
    VideoInfo,
    VoiceInfo,
)

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, list[str]] = {
    0: [
        """\
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    INTEGER UNIQUE,
    user_id       TEXT    NOT NULL,
    bot_id        TEXT    NOT NULL DEFAULT '',
    msg_type      INTEGER NOT NULL DEFAULT 1,
    direction     INTEGER NOT NULL DEFAULT 1,
    text          TEXT,
    timestamp_ms  INTEGER NOT NULL DEFAULT 0,
    context_token TEXT    NOT NULL DEFAULT '',
    data          TEXT    NOT NULL DEFAULT '{}',
    stored_at     REAL    NOT NULL
)""",
        "CREATE INDEX IF NOT EXISTS idx_msg_user_ts ON messages(user_id, timestamp_ms DESC)",
        "CREATE INDEX IF NOT EXISTS idx_msg_bot_ts ON messages(bot_id, timestamp_ms DESC)",
        "CREATE INDEX IF NOT EXISTS idx_msg_ts ON messages(timestamp_ms DESC)",
        "CREATE INDEX IF NOT EXISTS idx_msg_direction ON messages(direction, timestamp_ms DESC)",
    ],
}

# Auto-prune interval (number of inserts between prune runs).
_PRUNE_INTERVAL = 100


# ------------------------------------------------------------------
# Serialization helpers
# ------------------------------------------------------------------


def _serialize_media_info(mi: MediaInfo) -> dict[str, Any]:
    """Serialize a MediaInfo to a JSON-friendly dict."""
    return {
        "encrypt_query_param": mi.encrypt_query_param,
        "aes_key": mi.aes_key,
        "encrypt_type": mi.encrypt_type,
    }


def _deserialize_media_info(d: dict[str, Any]) -> MediaInfo:
    """Reconstruct a MediaInfo from its dict representation."""
    return MediaInfo(
        encrypt_query_param=d.get("encrypt_query_param", ""),
        aes_key=d.get("aes_key", ""),
        encrypt_type=d.get("encrypt_type", 0),
    )


def _serialize_image(img: ImageInfo) -> dict[str, Any]:
    return {
        "media": _serialize_media_info(img.media),
        "url": img.url,
        "thumb_width": img.thumb_width,
        "thumb_height": img.thumb_height,
        "hd_size": img.hd_size,
    }


def _deserialize_image(d: dict[str, Any]) -> ImageInfo:
    return ImageInfo(
        media=_deserialize_media_info(d.get("media", {})),
        url=d.get("url", ""),
        thumb_width=d.get("thumb_width", 0),
        thumb_height=d.get("thumb_height", 0),
        hd_size=d.get("hd_size", 0),
    )


def _serialize_voice(v: VoiceInfo) -> dict[str, Any]:
    return {
        "media": _serialize_media_info(v.media),
        "playtime": v.playtime,
        "text": v.text,
        "encode_type": v.encode_type,
        "bits_per_sample": v.bits_per_sample,
        "sample_rate": v.sample_rate,
    }


def _deserialize_voice(d: dict[str, Any]) -> VoiceInfo:
    return VoiceInfo(
        media=_deserialize_media_info(d.get("media", {})),
        playtime=d.get("playtime", 0),
        text=d.get("text", ""),
        encode_type=d.get("encode_type", 0),
        bits_per_sample=d.get("bits_per_sample", 0),
        sample_rate=d.get("sample_rate", 0),
    )


def _serialize_file(f: FileInfo) -> dict[str, Any]:
    return {
        "media": _serialize_media_info(f.media),
        "file_name": f.file_name,
        "file_size": f.file_size,
        "md5": f.md5,
    }


def _deserialize_file(d: dict[str, Any]) -> FileInfo:
    return FileInfo(
        media=_deserialize_media_info(d.get("media", {})),
        file_name=d.get("file_name", ""),
        file_size=d.get("file_size", ""),
        md5=d.get("md5", ""),
    )


def _serialize_video(v: VideoInfo) -> dict[str, Any]:
    return {
        "media": _serialize_media_info(v.media),
        "play_length": v.play_length,
        "video_md5": v.video_md5,
        "thumb_width": v.thumb_width,
        "thumb_height": v.thumb_height,
    }


def _deserialize_video(d: dict[str, Any]) -> VideoInfo:
    return VideoInfo(
        media=_deserialize_media_info(d.get("media", {})),
        play_length=d.get("play_length", 0),
        video_md5=d.get("video_md5", ""),
        thumb_width=d.get("thumb_width", 0),
        thumb_height=d.get("thumb_height", 0),
    )


def _serialize_ref_msg(r: RefMessage) -> dict[str, Any]:
    d: dict[str, Any] = {"msg_type": r.msg_type.value}
    if r.text is not None:
        d["text"] = r.text
    if r.image is not None:
        d["image"] = _serialize_image(r.image)
    if r.voice is not None:
        d["voice"] = _serialize_voice(r.voice)
    if r.file is not None:
        d["file"] = _serialize_file(r.file)
    if r.video is not None:
        d["video"] = _serialize_video(r.video)
    return d


def _deserialize_ref_msg(d: dict[str, Any]) -> RefMessage:
    mt = d.get("msg_type", 1)
    return RefMessage(
        msg_type=MessageType(mt)
        if mt in MessageType.__members__.values()
        else MessageType.TEXT,
        text=d.get("text"),
        image=_deserialize_image(d["image"]) if "image" in d else None,
        voice=_deserialize_voice(d["voice"]) if "voice" in d else None,
        file=_deserialize_file(d["file"]) if "file" in d else None,
        video=_deserialize_video(d["video"]) if "video" in d else None,
    )


def serialize_message(msg: Message) -> str:
    """Full lossless JSON serialization of a Message, preserving MediaInfo.

    Unlike ``Message.to_dict()`` (which strips CDN references for API
    output), this preserves all fields needed for ``download_media()``.

    Args:
        msg: The message to serialize.

    Returns:
        A JSON string.
    """
    d: dict[str, Any] = {
        "from_user": msg.from_user,
        "msg_type": msg.msg_type.value,
        "timestamp": msg.timestamp,
        "message_id": msg.message_id,
        "context_token": msg.context_token,
        "bot_id": msg.bot_id,
    }
    if msg.text is not None:
        d["text"] = msg.text
    if msg.image is not None:
        d["image"] = _serialize_image(msg.image)
    if msg.voice is not None:
        d["voice"] = _serialize_voice(msg.voice)
    if msg.file is not None:
        d["file"] = _serialize_file(msg.file)
    if msg.video is not None:
        d["video"] = _serialize_video(msg.video)
    if msg.ref_msg is not None:
        d["ref_msg"] = _serialize_ref_msg(msg.ref_msg)
    return json.dumps(d, ensure_ascii=False)


def deserialize_message(data: str) -> Message:
    """Reconstruct a Message from its JSON serialization.

    Args:
        data: JSON string produced by ``serialize_message()``.

    Returns:
        A reconstructed Message instance.
    """
    d = json.loads(data)
    mt = d.get("msg_type", 1)
    return Message(
        from_user=d.get("from_user", ""),
        msg_type=MessageType(mt)
        if mt in MessageType.__members__.values()
        else MessageType.TEXT,
        text=d.get("text"),
        image=_deserialize_image(d["image"]) if "image" in d else None,
        voice=_deserialize_voice(d["voice"]) if "voice" in d else None,
        file=_deserialize_file(d["file"]) if "file" in d else None,
        video=_deserialize_video(d["video"]) if "video" in d else None,
        timestamp=d.get("timestamp", 0),
        message_id=d.get("message_id"),
        context_token=d.get("context_token", ""),
        bot_id=d.get("bot_id"),
        ref_msg=_deserialize_ref_msg(d["ref_msg"]) if "ref_msg" in d else None,
    )


# ------------------------------------------------------------------
# MessageStore
# ------------------------------------------------------------------


class MessageStore:
    """SQLite-backed message persistence.

    Thread-safe.  Uses WAL mode for concurrent reader/writer access.
    Cross-process safe via SQLite's own locking.

    Args:
        db_path: Path to the SQLite database file.
        max_age_days: Auto-prune messages older than this (None to disable).
        max_count: Auto-prune when total exceeds this (None to disable).
    """

    def __init__(
        self,
        db_path: Path,
        *,
        max_age_days: int | None = 30,
        max_count: int | None = 100_000,
    ) -> None:
        self._db_path = Path(db_path)
        self._max_age_days = max_age_days
        self._max_count = max_count
        self._lock = threading.Lock()
        self._insert_count = 0
        self._closed = False

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=10.0,
        )
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._migrate()
        self.prune()

        logger.debug("MessageStore opened: %s", self._db_path)

    # ------------------------------------------------------------------
    # Schema migration
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        cur_version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        for version in range(cur_version, _SCHEMA_VERSION):
            for sql in _MIGRATIONS[version]:
                self._conn.execute(sql)
            self._conn.execute(f"PRAGMA user_version = {version + 1}")
        self._conn.commit()

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store(self, messages: list[Message], *, direction: int = 1) -> None:
        """Persist messages.  Idempotent via INSERT OR IGNORE on message_id.

        Args:
            messages: List of Message objects to store.
            direction: 1 = received (user→bot), 2 = sent (bot→user).
        """
        if not messages or self._closed:
            return
        now = time.time()
        rows = []
        for msg in messages:
            rows.append(
                (
                    msg.message_id,
                    msg.from_user,
                    msg.bot_id or "",
                    msg.msg_type.value,
                    direction,
                    msg.text,
                    msg.timestamp,
                    msg.context_token,
                    serialize_message(msg),
                    now,
                )
            )
        with self._lock:
            self._conn.executemany(
                "INSERT OR IGNORE INTO messages "
                "(message_id, user_id, bot_id, msg_type, direction, text, "
                "timestamp_ms, context_token, data, stored_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
            self._insert_count += len(rows)
            if self._insert_count >= _PRUNE_INTERVAL:
                self._insert_count = 0
                self._prune_locked()

    def store_sent(
        self,
        user_id: str,
        bot_id: str,
        text: str | None = None,
        msg_type: MessageType = MessageType.TEXT,
    ) -> None:
        """Record an outbound message (no iLink message_id).

        Args:
            user_id: Target user ID.
            bot_id: Bot session ID.
            text: Text content.
            msg_type: Message type.
        """
        now = time.time()
        timestamp_ms = int(now * 1000)
        msg = Message(
            from_user=user_id,
            msg_type=msg_type,
            text=text,
            timestamp=timestamp_ms,
            bot_id=bot_id,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages "
                "(message_id, user_id, bot_id, msg_type, direction, text, "
                "timestamp_ms, context_token, data, stored_at) "
                "VALUES (NULL, ?, ?, ?, 2, ?, ?, '', ?, ?)",
                (
                    user_id,
                    bot_id,
                    msg_type.value,
                    text,
                    timestamp_ms,
                    serialize_message(msg),
                    now,
                ),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_by_id(self, message_id: int) -> Message | None:
        """Look up a single message by iLink message_id.

        Args:
            message_id: The iLink message ID.

        Returns:
            The reconstructed Message, or None if not found.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        if row is None:
            return None
        return deserialize_message(row[0])

    def query(
        self,
        *,
        user_id: str | None = None,
        bot_id: str | None = None,
        msg_type: int | None = None,
        direction: int | None = None,
        since_ms: int | None = None,
        until_ms: int | None = None,
        text_contains: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query message history.

        Args:
            user_id: Filter by WeChat user ID.
            bot_id: Filter by bot session ID.
            msg_type: Filter by MessageType value (1-5).
            direction: Filter by direction (1=received, 2=sent).
            since_ms: Start time (unix milliseconds, inclusive).
            until_ms: End time (unix milliseconds, inclusive).
            text_contains: Case-insensitive text substring search.
            limit: Maximum results (capped at 200).
            offset: Pagination offset.

        Returns:
            List of message dicts (to_dict format + direction field).
        """
        if self._closed:
            return []
        limit = min(limit, 200)
        clauses: list[str] = []
        params: list[Any] = []

        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if bot_id:
            clauses.append("bot_id = ?")
            params.append(bot_id)
        if msg_type is not None:
            clauses.append("msg_type = ?")
            params.append(msg_type)
        if direction is not None:
            clauses.append("direction = ?")
            params.append(direction)
        if since_ms is not None:
            clauses.append("timestamp_ms >= ?")
            params.append(since_ms)
        if until_ms is not None:
            clauses.append("timestamp_ms <= ?")
            params.append(until_ms)
        if text_contains:
            clauses.append("text LIKE ?")
            params.append(f"%{text_contains}%")

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT data, direction FROM messages{where} ORDER BY timestamp_ms DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        results = []
        for data_json, row_dir in rows:
            try:
                msg = deserialize_message(data_json)
                d = msg.to_dict()
                d["direction"] = "received" if row_dir == 1 else "sent"
                results.append(d)
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("Failed to deserialize message: %s", data_json[:100])
        return results

    def query_messages(
        self,
        *,
        bot_id: str | None = None,
        direction: int | None = None,
        since_ms: int | None = None,
        limit: int = 200,
    ) -> list[Message]:
        """Query messages and return Message objects directly.

        A lightweight variant of ``query()`` that skips the dict conversion,
        intended for internal use by the cooperative-polling fallback
        (Route C).

        Args:
            bot_id: Filter by bot session ID.
            direction: Filter by direction (1=received, 2=sent).
            since_ms: Start time (unix milliseconds, inclusive).
            limit: Maximum results (capped at 200).

        Returns:
            List of Message objects, newest first.
        """
        if self._closed:
            return []
        limit = min(limit, 200)
        clauses: list[str] = []
        params: list[Any] = []

        if bot_id:
            clauses.append("bot_id = ?")
            params.append(bot_id)
        if direction is not None:
            clauses.append("direction = ?")
            params.append(direction)
        if since_ms is not None:
            clauses.append("timestamp_ms >= ?")
            params.append(since_ms)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT data FROM messages{where} ORDER BY timestamp_ms DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        results: list[Message] = []
        for (data_json,) in rows:
            try:
                results.append(deserialize_message(data_json))
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("Failed to deserialize message: %s", data_json[:100])
        return results

    def count(
        self,
        *,
        user_id: str | None = None,
        bot_id: str | None = None,
        msg_type: int | None = None,
        direction: int | None = None,
        since_ms: int | None = None,
        until_ms: int | None = None,
        text_contains: str | None = None,
    ) -> int:
        """Count messages matching filter criteria.

        Args:
            Same filter parameters as ``query()``.

        Returns:
            Number of matching messages.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if bot_id:
            clauses.append("bot_id = ?")
            params.append(bot_id)
        if msg_type is not None:
            clauses.append("msg_type = ?")
            params.append(msg_type)
        if direction is not None:
            clauses.append("direction = ?")
            params.append(direction)
        if since_ms is not None:
            clauses.append("timestamp_ms >= ?")
            params.append(since_ms)
        if until_ms is not None:
            clauses.append("timestamp_ms <= ?")
            params.append(until_ms)
        if text_contains:
            clauses.append("text LIKE ?")
            params.append(f"%{text_contains}%")

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) FROM messages{where}", params
            ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def prune(self) -> int:
        """Delete messages older than max_age_days or exceeding max_count.

        Returns:
            Number of rows deleted.
        """
        with self._lock:
            return self._prune_locked()

    def _prune_locked(self) -> int:
        """Prune implementation, must be called with _write_lock held."""
        deleted = 0

        if self._max_age_days is not None:
            cutoff = time.time() - self._max_age_days * 86400
            cur = self._conn.execute(
                "DELETE FROM messages WHERE stored_at < ?", (cutoff,)
            )
            deleted += cur.rowcount

        if self._max_count is not None:
            cur = self._conn.execute(
                "DELETE FROM messages WHERE id NOT IN "
                "(SELECT id FROM messages ORDER BY timestamp_ms DESC LIMIT ?)",
                (self._max_count,),
            )
            deleted += cur.rowcount

        if deleted:
            self._conn.commit()
            logger.debug("Pruned %d old message(s)", deleted)

        return deleted

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._closed = True
        try:
            self._conn.close()
        except Exception:
            pass
        logger.debug("MessageStore closed: %s", self._db_path)
