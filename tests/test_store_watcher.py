"""Tests for the store-watcher dispatcher fallback."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from weilink._store import MessageStore
from weilink._vendor.filelock import FileLock
from weilink.client import WeiLink
from weilink.models import Message, MessageType


def _make_msg(
    text: str = "hello",
    from_user: str = "user1@im.wechat",
    bot_id: str = "bot1@im.bot",
    message_id: int | None = 100,
    timestamp: int = 1700000000000,
) -> Message:
    return Message(
        from_user=from_user,
        msg_type=MessageType.TEXT,
        text=text,
        timestamp=timestamp,
        message_id=message_id,
        bot_id=bot_id,
    )


# ------------------------------------------------------------------
# MessageStore: max_rowid / query_since_rowid
# ------------------------------------------------------------------


class TestStoreRowidQueries:
    def test_max_rowid_empty(self, tmp_path: Path) -> None:
        store = MessageStore(tmp_path / "test.db")
        assert store.max_rowid() == 0
        store.close()

    def test_max_rowid_after_insert(self, tmp_path: Path) -> None:
        store = MessageStore(tmp_path / "test.db")
        store.store([_make_msg(message_id=1)])
        assert store.max_rowid() >= 1
        store.store([_make_msg(message_id=2)])
        assert store.max_rowid() >= 2
        store.close()

    def test_query_since_rowid_empty(self, tmp_path: Path) -> None:
        store = MessageStore(tmp_path / "test.db")
        msgs, hwm = store.query_since_rowid(0)
        assert msgs == []
        assert hwm == 0
        store.close()

    def test_query_since_rowid_returns_new(self, tmp_path: Path) -> None:
        store = MessageStore(tmp_path / "test.db")
        store.store([_make_msg(text="first", message_id=1)])
        hwm = store.max_rowid()

        store.store([_make_msg(text="second", message_id=2)])
        msgs, new_hwm = store.query_since_rowid(hwm)
        assert len(msgs) == 1
        assert msgs[0].text == "second"
        assert new_hwm > hwm
        store.close()

    def test_query_since_rowid_skips_old(self, tmp_path: Path) -> None:
        store = MessageStore(tmp_path / "test.db")
        store.store([_make_msg(text="old", message_id=1)])
        store.store([_make_msg(text="also old", message_id=2)])
        hwm = store.max_rowid()

        msgs, new_hwm = store.query_since_rowid(hwm)
        assert msgs == []
        assert new_hwm == hwm
        store.close()

    def test_query_since_rowid_chronological_order(self, tmp_path: Path) -> None:
        store = MessageStore(tmp_path / "test.db")
        hwm = store.max_rowid()
        store.store([_make_msg(text="a", message_id=1, timestamp=1000)])
        store.store([_make_msg(text="b", message_id=2, timestamp=2000)])
        store.store([_make_msg(text="c", message_id=3, timestamp=3000)])

        msgs, _ = store.query_since_rowid(hwm)
        assert [m.text for m in msgs] == ["a", "b", "c"]
        store.close()

    def test_query_since_rowid_direction_filter(self, tmp_path: Path) -> None:
        store = MessageStore(tmp_path / "test.db")
        hwm = store.max_rowid()
        store.store([_make_msg(text="received", message_id=1)])
        store.store_sent("user1@im.wechat", "bot1@im.bot", text="sent")

        msgs_recv, _ = store.query_since_rowid(hwm, direction=1)
        assert len(msgs_recv) == 1
        assert msgs_recv[0].text == "received"

        msgs_all, _ = store.query_since_rowid(hwm)
        assert len(msgs_all) == 2
        store.close()


# ------------------------------------------------------------------
# Store watcher integration
# ------------------------------------------------------------------


class TestStoreWatcher:
    def test_dispatch_to_handlers(self, tmp_path: Path) -> None:
        """Store watcher dispatches new messages to on_message handlers."""
        wl = WeiLink(
            token_path=tmp_path / "token.json",
            message_store=tmp_path / "messages.db",
        )
        received: list[Message] = []

        @wl.on_message
        def handler(msg: Message) -> None:
            received.append(msg)

        # Use a separate FileLock instance to simulate another process
        # holding the poll lock. Same-instance lock is re-entrant on Unix.
        external_lock = FileLock(tmp_path / ".poll.lock")
        external_lock.lock()
        try:
            wl.run_background()

            # Insert a message into the store (simulating another process).
            assert wl._message_store is not None
            wl._message_store.store([_make_msg(text="watcher test", message_id=42)])

            # Wait for the store watcher to pick it up.
            deadline = time.monotonic() + 5.0
            while not received and time.monotonic() < deadline:
                time.sleep(0.2)

            assert len(received) == 1
            assert received[0].text == "watcher test"
        finally:
            wl.stop()
            external_lock.unlock()
            external_lock.close()
            wl.close()

    def test_enqueues_for_recv(self, tmp_path: Path) -> None:
        """Store watcher enqueues messages for recv() consumers."""
        wl = WeiLink(
            token_path=tmp_path / "token.json",
            message_store=tmp_path / "messages.db",
        )

        external_lock = FileLock(tmp_path / ".poll.lock")
        external_lock.lock()
        try:
            wl.run_background()

            assert wl._message_store is not None
            wl._message_store.store([_make_msg(text="queue test", message_id=43)])

            # recv should return the message from the queue.
            msgs = wl.recv(timeout=5.0)
            assert len(msgs) >= 1
            assert any(m.text == "queue test" for m in msgs)
        finally:
            wl.stop()
            external_lock.unlock()
            external_lock.close()
            wl.close()

    def test_skips_existing_messages(self, tmp_path: Path) -> None:
        """Messages already in the store before start are not dispatched."""
        wl = WeiLink(
            token_path=tmp_path / "token.json",
            message_store=tmp_path / "messages.db",
        )
        received: list[Message] = []

        @wl.on_message
        def handler(msg: Message) -> None:
            received.append(msg)

        # Insert BEFORE starting dispatcher.
        assert wl._message_store is not None
        wl._message_store.store([_make_msg(text="old msg", message_id=99)])

        external_lock = FileLock(tmp_path / ".poll.lock")
        external_lock.lock()
        try:
            wl.run_background()
            # Wait a couple of watch intervals.
            time.sleep(3.0)
            assert len(received) == 0
        finally:
            wl.stop()
            external_lock.unlock()
            external_lock.close()
            wl.close()

    def test_start_dispatcher_raises_without_store(self, tmp_path: Path) -> None:
        """RuntimeError if poll lock held and no message_store."""
        wl = WeiLink(token_path=tmp_path / "token.json")

        external_lock = FileLock(tmp_path / ".poll.lock")
        external_lock.lock()
        try:
            with pytest.raises(RuntimeError, match="message_store is not enabled"):
                wl.run_background()
        finally:
            external_lock.unlock()
            external_lock.close()
            wl.close()

    def test_start_dispatcher_uses_poll_loop_when_free(self, tmp_path: Path) -> None:
        """When poll lock is free, normal poll loop is used (not store watcher)."""
        wl = WeiLink(
            token_path=tmp_path / "token.json",
            message_store=tmp_path / "messages.db",
        )
        try:
            wl.run_background()
            # The thread target should be _poll_loop, not _store_watch_loop
            assert wl._dispatcher_thread is not None
            # Can't easily check target, but if it started without error
            # and poll lock is free, it's using _poll_loop.
            assert wl._dispatcher_thread.is_alive()
        finally:
            wl.stop()
            wl.close()
