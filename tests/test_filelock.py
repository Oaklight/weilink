"""Tests for the cross-process file-lock helper."""

import os
import sys
import tempfile
from pathlib import Path


from weilink.filelock import FileLock


class TestFileLock:
    """Cross-platform file lock tests (Unix fcntl + Windows msvcrt)."""

    def test_lock_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".lock"
            lock = FileLock(lock_path)
            lock.lock()
            assert lock_path.exists()
            lock.unlock()
            lock.close()

    def test_context_manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".lock"
            lock = FileLock(lock_path)
            with lock:
                assert lock_path.exists()
            lock.close()

    def test_try_lock_succeeds_when_free(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".lock"
            lock = FileLock(lock_path)
            assert lock.try_lock() is True
            lock.unlock()
            lock.close()

    def test_try_lock_fails_when_held(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".lock"
            # Holder acquires lock via a separate fd
            holder_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)

            if sys.platform == "win32":
                import msvcrt

                os.write(holder_fd, b"\x00")
                os.lseek(holder_fd, 0, os.SEEK_SET)
                msvcrt.locking(holder_fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(holder_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            try:
                lock = FileLock(lock_path)
                assert lock.try_lock() is False
                lock.close()
            finally:
                if sys.platform == "win32":
                    os.lseek(holder_fd, 0, os.SEEK_SET)
                    msvcrt.locking(holder_fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(holder_fd, fcntl.LOCK_UN)
                os.close(holder_fd)

    def test_unlock_releases_for_others(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".lock"
            lock_a = FileLock(lock_path)
            lock_b = FileLock(lock_path)

            lock_a.lock()
            assert lock_b.try_lock() is False

            lock_a.unlock()
            assert lock_b.try_lock() is True

            lock_b.unlock()
            lock_a.close()
            lock_b.close()

    def test_close_releases_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".lock"
            lock_a = FileLock(lock_path)
            lock_b = FileLock(lock_path)

            lock_a.lock()
            assert lock_b.try_lock() is False

            lock_a.close()  # close fd => lock released
            assert lock_b.try_lock() is True

            lock_b.unlock()
            lock_b.close()

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "sub" / "dir" / ".lock"
            lock = FileLock(lock_path)
            lock.lock()
            assert lock_path.exists()
            lock.unlock()
            lock.close()

    def test_double_close_is_safe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".lock"
            lock = FileLock(lock_path)
            lock.lock()
            lock.close()
            lock.close()  # should not raise
