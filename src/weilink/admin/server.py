"""HTTP server for admin panel."""

from __future__ import annotations

import logging
import socket
import threading
from dataclasses import dataclass
from http.server import HTTPServer
from typing import TYPE_CHECKING

from .handlers import AdminRequestHandler

if TYPE_CHECKING:
    from weilink.client import WeiLink

logger = logging.getLogger(__name__)


@dataclass
class AdminInfo:
    """Information about the running admin server.

    Attributes:
        host: The host address the server is bound to.
        port: The port number the server is listening on.
        url: The full URL to access the admin panel.
    """

    host: str
    port: int
    url: str


class AdminServer:
    """Admin panel HTTP server running in a background thread.

    Example::

        from weilink import WeiLink

        wl = WeiLink()
        wl.login()
        info = wl.start_admin(port=8080)
        print(f"Admin panel at: {info.url}")
    """

    def __init__(
        self,
        weilink: WeiLink,
        host: str = "127.0.0.1",
        port: int = 8080,
    ) -> None:
        """Initialize admin server.

        Args:
            weilink: The WeiLink client instance to manage.
            host: The host address to bind to.
            port: The port number to listen on.
        """
        self._weilink = weilink
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()

    def start(self) -> AdminInfo:
        """Start the server in a background daemon thread.

        Returns:
            AdminInfo with host, port, and URL.

        Raises:
            RuntimeError: If the server is already running.
        """
        if self._server is not None:
            raise RuntimeError("Admin server is already running")

        if self._port != 0:
            actual_port = self._find_available_port(self._host, self._port)
            self._port = actual_port

        handler_class = type(
            "BoundAdminHandler",
            (AdminRequestHandler,),
            {"weilink": self._weilink},
        )

        self._server = HTTPServer((self._host, self._port), handler_class)
        # Retrieve the actual port (important when port=0 for OS-assigned)
        self._port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started.wait(timeout=5.0)

        display_host = (
            "localhost" if self._host in ("0.0.0.0", "127.0.0.1") else self._host
        )
        url = f"http://{display_host}:{self._port}"

        info = AdminInfo(host=self._host, port=self._port, url=url)
        logger.info("Admin server started at %s", url)
        return info

    def _run(self) -> None:
        """Run the server (called in background thread)."""
        self._started.set()
        if self._server:
            self._server.serve_forever()

    def stop(self) -> None:
        """Stop the server."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._started.clear()
            logger.info("Admin server stopped")

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def is_running(self) -> bool:
        """Check if server is running."""
        return self._server is not None and self._started.is_set()

    def get_info(self) -> AdminInfo | None:
        """Get server info if running."""
        if not self.is_running():
            return None

        display_host = (
            "localhost" if self._host in ("0.0.0.0", "127.0.0.1") else self._host
        )
        return AdminInfo(
            host=self._host,
            port=self._port,
            url=f"http://{display_host}:{self._port}",
        )

    @staticmethod
    def _find_available_port(host: str, start_port: int) -> int:
        """Find an available port starting from start_port."""
        for port in range(start_port, start_port + 100):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind((host, port))
                    return port
            except OSError:
                continue

        raise RuntimeError(f"No available port in range {start_port}-{start_port + 99}")
