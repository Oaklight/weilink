# /// zerodep
# version = "0.3.0"
# deps = []
# tier = "simple"
# category = "utility"
# ///

"""Cross-process file locking (Unix ``fcntl`` / Windows ``msvcrt``).

Part of zerodep: https://github.com/Oaklight/zerodep
Copyright (c) 2026 Peng Ding. MIT License.

A cross-platform, context-manager-based advisory file lock using only the
Python standard library.  On Unix/macOS it delegates to ``fcntl.flock``;
on Windows it uses ``msvcrt.locking`` with exponential-backoff polling for
blocking semantics.

Usage::

    from filelock import FileLock
    from pathlib import Path

    lock = FileLock(Path("/tmp/.my.lock"))

    # Blocking acquire
    with lock:
        ...  # exclusive access

    # Non-blocking try
    if lock.try_lock():
        try:
            ...
        finally:
            lock.unlock()

Requirements:
    Python >= 3.10, no third-party packages.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

__all__ = [
    "FileLock",
]

# ── Platform detection ────────────────────────────────────────────────

_IS_WIN32 = sys.platform == "win32"

if _IS_WIN32:
    import msvcrt
else:
    import fcntl


# ── FileLock ──────────────────────────────────────────────────────────


class FileLock:
    """Advisory file lock backed by ``fcntl.flock`` (Unix) or
    ``msvcrt.locking`` (Windows).

    The lock is *advisory* — it coordinates only among processes that
    voluntarily use the same lock file.  It is **not** reentrant within a
    single OS thread (locking twice from the same ``FileLock`` instance
    without an intermediate unlock is safe because ``fcntl.flock`` /
    ``msvcrt.locking`` silently succeed, but two *different* ``FileLock``
    objects pointing at the same path will deadlock on Unix).

    Args:
        path: Path to the lock file (created automatically if missing,
            along with any intermediate parent directories).

    Attributes:
        path: The lock-file path supplied at construction time.
    """

    # msvcrt.locking requires a byte-range length; we lock the first byte.
    _LOCK_LEN = 1

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._fd: int | None = None

    # ── Properties ────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        """The lock-file path."""
        return self._path

    # ── Public API ────────────────────────────────────────────────────

    def lock(self) -> None:
        """Acquire the lock, blocking until available."""
        self._ensure_fd()
        assert self._fd is not None
        if _IS_WIN32:
            self._win_lock_blocking()
        else:
            fcntl.flock(self._fd, fcntl.LOCK_EX)

    def try_lock(self) -> bool:
        """Try to acquire the lock without blocking.

        Returns:
            ``True`` if the lock was acquired, ``False`` if another
            process holds it.
        """
        self._ensure_fd()
        assert self._fd is not None
        if _IS_WIN32:
            return self._win_try_lock()
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def unlock(self) -> None:
        """Release the lock (no-op if not held)."""
        if self._fd is None:
            return
        if _IS_WIN32:
            self._win_unlock()
        else:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass

    def close(self) -> None:
        """Release the lock and close the underlying file descriptor."""
        if self._fd is not None:
            try:
                self.unlock()
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    # ── Context manager ───────────────────────────────────────────────

    def __enter__(self) -> FileLock:
        self.lock()
        return self

    def __exit__(self, *args: object) -> None:
        self.unlock()

    # ── Internals ─────────────────────────────────────────────────────

    def _ensure_fd(self) -> None:
        """Open (or create) the lock file if not already open."""
        if self._fd is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(
            str(self._path),
            os.O_RDWR | os.O_CREAT,
            0o644,
        )
        if _IS_WIN32:
            # Ensure the file has at least 1 byte so msvcrt.locking works.
            if os.fstat(self._fd).st_size == 0:
                os.write(self._fd, b"\x00")
            os.lseek(self._fd, 0, os.SEEK_SET)

    # ── Windows helpers ───────────────────────────────────────────────

    def _win_try_lock(self) -> bool:
        """Non-blocking lock via ``msvcrt.LK_NBLCK``."""
        assert self._fd is not None
        os.lseek(self._fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(self._fd, msvcrt.LK_NBLCK, self._LOCK_LEN)
            return True
        except OSError:
            return False

    def _win_lock_blocking(self) -> None:
        """Blocking lock via polling ``msvcrt.LK_NBLCK``.

        ``msvcrt.LK_LOCK`` retries internally but only for ~1 s.
        We spin with back-off for robust blocking semantics.
        """
        assert self._fd is not None
        delay = 0.01
        while True:
            if self._win_try_lock():
                return
            time.sleep(delay)
            delay = min(delay * 2, 0.5)

    def _win_unlock(self) -> None:
        """Unlock via ``msvcrt.LK_UNLCK``."""
        assert self._fd is not None
        os.lseek(self._fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(self._fd, msvcrt.LK_UNLCK, self._LOCK_LEN)
        except OSError:
            pass
