"""Cross-process file locking via ``fcntl.flock``.

Provides :class:`FileLock`, a reentrant-safe, context-manager-based file
lock used to coordinate access to shared profile files (``token.json``,
``contexts.json``) across multiple WeiLink processes.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# fcntl is Unix-only; on Windows we degrade gracefully (no locking).
if sys.platform != "win32":
    import fcntl

    _HAS_FCNTL = True
else:
    _HAS_FCNTL = False


class FileLock:
    """Advisory file lock backed by ``fcntl.flock``.

    Args:
        path: Path to the lock file (created if missing).

    Usage::

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
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lock(self) -> None:
        """Acquire the lock, blocking until available."""
        if not _HAS_FCNTL:
            return
        self._ensure_fd()
        assert self._fd is not None
        fcntl.flock(self._fd, fcntl.LOCK_EX)

    def try_lock(self) -> bool:
        """Try to acquire the lock without blocking.

        Returns:
            ``True`` if the lock was acquired, ``False`` if another
            process holds it.
        """
        if not _HAS_FCNTL:
            return True
        self._ensure_fd()
        assert self._fd is not None
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def unlock(self) -> None:
        """Release the lock (no-op if not held)."""
        if not _HAS_FCNTL:
            return
        if self._fd is not None:
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

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> FileLock:
        self.lock()
        return self

    def __exit__(self, *args: object) -> None:
        self.unlock()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

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
