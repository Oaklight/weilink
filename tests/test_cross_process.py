"""Cross-process file locking integration tests.

These tests spawn real child processes to verify that poll_lock and
data_lock behave correctly across process boundaries.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import sys
import time
from pathlib import Path

import pytest

# Ensure the source tree is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from weilink._filelock import FileLock


# ── Helpers ──────────────────────────────────────────────────────────────


def _child_hold_poll_lock(base_path: str, ready_event, release_event):
    """Child process: acquire poll lock, signal ready, wait for release."""
    lock = FileLock(Path(base_path) / ".poll.lock")
    lock.lock()
    ready_event.set()
    release_event.wait(timeout=10)
    lock.unlock()
    lock.close()


def _child_try_poll_lock(base_path: str, result_queue):
    """Child process: try to acquire poll lock, report success/failure."""
    lock = FileLock(Path(base_path) / ".poll.lock")
    got_it = lock.try_lock()
    result_queue.put(got_it)
    if got_it:
        lock.unlock()
    lock.close()


def _child_hold_data_lock_and_write(base_path: str, ready_event, release_event):
    """Child process: acquire data lock, write to file, hold lock until signaled."""
    lock = FileLock(Path(base_path) / ".data.lock")
    lock.lock()
    ctx_path = Path(base_path) / "contexts.json"
    ctx_path.write_text(json.dumps({"writer": "child_a", "ts": time.time()}))
    ready_event.set()
    release_event.wait(timeout=10)
    lock.unlock()
    lock.close()


def _child_data_lock_read(base_path: str, ready_event, result_queue):
    """Child process: wait for ready, then acquire data lock and read file."""
    ready_event.wait(timeout=10)
    lock = FileLock(Path(base_path) / ".data.lock")
    lock.lock()
    ctx_path = Path(base_path) / "contexts.json"
    data = json.loads(ctx_path.read_text())
    result_queue.put(data)
    lock.unlock()
    lock.close()


def _child_concurrent_increment(base_path: str, n_iterations: int, worker_id: str):
    """Child process: repeatedly read-increment-write a counter under data lock."""
    lock = FileLock(Path(base_path) / ".data.lock")
    counter_path = Path(base_path) / "counter.json"

    for _ in range(n_iterations):
        lock.lock()
        try:
            data = json.loads(counter_path.read_text())
            data["count"] += 1
            data["last_writer"] = worker_id
            counter_path.write_text(json.dumps(data))
        finally:
            lock.unlock()


# ── Tests ────────────────────────────────────────────────────────────────


class TestCrossProcessPollLock:
    """Verify that poll_lock prevents concurrent recv across processes."""

    def test_second_process_fails_try_lock(self, tmp_path):
        """When process A holds poll_lock, process B's try_lock returns False."""
        base = str(tmp_path)
        ready = multiprocessing.Event()
        release = multiprocessing.Event()
        result_q = multiprocessing.Queue()

        # Process A grabs poll_lock
        proc_a = multiprocessing.Process(
            target=_child_hold_poll_lock, args=(base, ready, release)
        )
        proc_a.start()
        ready.wait(timeout=5)
        assert ready.is_set(), "Child A did not acquire lock in time"

        # Process B tries poll_lock — should fail
        proc_b = multiprocessing.Process(
            target=_child_try_poll_lock, args=(base, result_q)
        )
        proc_b.start()
        proc_b.join(timeout=5)
        got_lock = result_q.get(timeout=2)
        assert got_lock is False, "Process B should NOT have acquired poll_lock"

        # Release A
        release.set()
        proc_a.join(timeout=5)

    def test_many_processes_only_one_wins(self, tmp_path):
        """With N processes racing for poll_lock, exactly one succeeds."""
        base = str(tmp_path)
        n_procs = 8
        result_q = multiprocessing.Queue()

        # Barrier ensures all children start try_lock at roughly the same time
        barrier = multiprocessing.Barrier(n_procs)

        def _race_try_lock(base_path, barrier, result_queue):
            lock = FileLock(Path(base_path) / ".poll.lock")
            barrier.wait(timeout=10)
            got_it = lock.try_lock()
            result_queue.put(got_it)
            if got_it:
                time.sleep(0.2)  # hold briefly so others see it as taken
                lock.unlock()
            lock.close()

        procs = []
        for _ in range(n_procs):
            p = multiprocessing.Process(
                target=_race_try_lock, args=(base, barrier, result_q)
            )
            procs.append(p)
            p.start()

        for p in procs:
            p.join(timeout=10)

        results = [result_q.get(timeout=2) for _ in range(n_procs)]
        winners = results.count(True)
        assert winners == 1, (
            f"Exactly 1 process should win poll_lock, but {winners} did"
        )

    def test_lock_available_after_release(self, tmp_path):
        """After process A releases poll_lock, process B can acquire it."""
        base = str(tmp_path)
        ready = multiprocessing.Event()
        release = multiprocessing.Event()

        proc_a = multiprocessing.Process(
            target=_child_hold_poll_lock, args=(base, ready, release)
        )
        proc_a.start()
        ready.wait(timeout=5)

        # Release A immediately
        release.set()
        proc_a.join(timeout=5)

        # Now B should succeed
        result_q = multiprocessing.Queue()
        proc_b = multiprocessing.Process(
            target=_child_try_poll_lock, args=(base, result_q)
        )
        proc_b.start()
        proc_b.join(timeout=5)
        got_lock = result_q.get(timeout=2)
        assert got_lock is True, "Process B should acquire poll_lock after A released"

    def test_lock_released_on_process_crash(self, tmp_path):
        """If the lock-holding process dies, the lock is released (advisory lock)."""
        base = str(tmp_path)
        ready = multiprocessing.Event()
        release = multiprocessing.Event()  # never set — simulate crash

        proc_a = multiprocessing.Process(
            target=_child_hold_poll_lock, args=(base, ready, release)
        )
        proc_a.start()
        ready.wait(timeout=5)

        # Kill process A (simulates crash)
        proc_a.terminate()
        proc_a.join(timeout=5)

        # Lock should be auto-released by OS
        result_q = multiprocessing.Queue()
        proc_b = multiprocessing.Process(
            target=_child_try_poll_lock, args=(base, result_q)
        )
        proc_b.start()
        proc_b.join(timeout=5)
        got_lock = result_q.get(timeout=2)
        assert got_lock is True, "Lock should be released when holding process dies"


class TestCrossProcessDataLock:
    """Verify that data_lock serializes file I/O across processes."""

    def test_blocked_until_lock_released(self, tmp_path):
        """Process B blocks on data_lock until process A releases it."""
        base = str(tmp_path)
        ready = multiprocessing.Event()
        release = multiprocessing.Event()
        result_q = multiprocessing.Queue()

        # Write initial context
        ctx_path = tmp_path / "contexts.json"
        ctx_path.write_text(json.dumps({"writer": "init"}))

        # A holds data lock and writes
        proc_a = multiprocessing.Process(
            target=_child_hold_data_lock_and_write, args=(base, ready, release)
        )
        proc_a.start()

        # B waits for A to be ready, then tries to acquire data lock
        proc_b = multiprocessing.Process(
            target=_child_data_lock_read, args=(base, ready, result_q)
        )
        proc_b.start()

        # Wait a moment — B should be blocked
        time.sleep(0.3)
        assert result_q.empty(), "B should be blocked while A holds data lock"

        # Release A — B should now proceed
        release.set()
        proc_a.join(timeout=5)
        proc_b.join(timeout=5)

        data = result_q.get(timeout=2)
        assert data["writer"] == "child_a", "B should read A's written data"

    def test_concurrent_increments_no_lost_updates(self, tmp_path):
        """Two processes incrementing a counter under data_lock lose no updates."""
        base = str(tmp_path)
        n_per_worker = 100
        counter_path = tmp_path / "counter.json"
        counter_path.write_text(json.dumps({"count": 0, "last_writer": ""}))

        proc_a = multiprocessing.Process(
            target=_child_concurrent_increment, args=(base, n_per_worker, "A")
        )
        proc_b = multiprocessing.Process(
            target=_child_concurrent_increment, args=(base, n_per_worker, "B")
        )
        proc_a.start()
        proc_b.start()
        proc_a.join(timeout=30)
        proc_b.join(timeout=30)

        data = json.loads(counter_path.read_text())
        expected = n_per_worker * 2
        assert data["count"] == expected, (
            f"Expected {expected} increments, got {data['count']} — lost updates!"
        )

    def test_many_processes_concurrent_increments(self, tmp_path):
        """N processes each incrementing a counter M times — no lost updates."""
        base = str(tmp_path)
        n_procs = 6
        n_per_worker = 50
        counter_path = tmp_path / "counter.json"
        counter_path.write_text(json.dumps({"count": 0, "last_writer": ""}))

        procs = []
        for i in range(n_procs):
            p = multiprocessing.Process(
                target=_child_concurrent_increment,
                args=(base, n_per_worker, f"W{i}"),
            )
            procs.append(p)
            p.start()

        for p in procs:
            p.join(timeout=30)

        data = json.loads(counter_path.read_text())
        expected = n_procs * n_per_worker
        assert data["count"] == expected, (
            f"Expected {expected} increments, got {data['count']} — lost updates!"
        )


class TestCrossProcessBothLocks:
    """Verify poll_lock and data_lock work together as designed."""

    def test_data_lock_independent_of_poll_lock(self, tmp_path):
        """Process A holds poll_lock; process B can still acquire data_lock."""
        base = str(tmp_path)
        ready = multiprocessing.Event()
        release = multiprocessing.Event()

        # A holds poll_lock
        proc_a = multiprocessing.Process(
            target=_child_hold_poll_lock, args=(base, ready, release)
        )
        proc_a.start()
        ready.wait(timeout=5)

        # B acquires data_lock — should succeed immediately
        data_lock = FileLock(tmp_path / ".data.lock")
        got_it = data_lock.try_lock()
        assert got_it is True, "data_lock should be independent of poll_lock"
        data_lock.unlock()
        data_lock.close()

        release.set()
        proc_a.join(timeout=5)
