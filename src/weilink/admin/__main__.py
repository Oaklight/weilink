"""Standalone admin panel server CLI.

Run as a long-lived process to manage WeiLink bot sessions via a web UI.
Suitable for Docker deployment or daemon usage.

Examples::

    # Default profile (~/.weilink/)
    weilink-admin --host 0.0.0.0 --port 8080

    # Custom profile for a different bot
    weilink-admin -d /data/bot-work -p 9090

    # Multiple instances with different profiles
    weilink-admin -d ~/.weilink/personal -p 8080 &
    weilink-admin -d ~/.weilink/work -p 8081 &
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading


def main(argv: list[str] | None = None) -> None:
    """Run the WeiLink admin panel as a standalone server."""
    parser = argparse.ArgumentParser(
        prog="weilink-admin",
        description="WeiLink admin panel — web UI for managing bot sessions.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host address to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8080,
        help="port number to listen on (default: 8080)",
    )
    parser.add_argument(
        "--base-path",
        "-d",
        default=None,
        help="WeiLink data directory / profile path (default: ~/.weilink/)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging level (default: INFO)",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from pathlib import Path

    from weilink import WeiLink

    kwargs: dict[str, Path] = {}
    if args.base_path:
        kwargs["base_path"] = Path(args.base_path)

    wl = WeiLink(**kwargs)
    info = wl.start_admin(host=args.host, port=args.port)

    print(f"WeiLink admin panel running at {info.url}")
    print(f"Data directory: {wl._base_path}")
    print("Press Ctrl+C to stop.")

    # Block until SIGINT/SIGTERM. signal.signal() only works in main thread,
    # so use try/except KeyboardInterrupt as fallback when called from a
    # non-main thread (e.g. tests).
    stop = threading.Event()

    def _handle_signal(signum: int, frame: object) -> None:
        print("\nShutting down...")
        stop.set()

    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except ValueError:
        # Not in main thread — stop event must be set externally
        pass

    stop.wait()
    wl.close()
    print("Admin panel stopped.")


if __name__ == "__main__":
    main()
