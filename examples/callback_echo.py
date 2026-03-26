"""Callback echo bot - event-driven message handling.

Usage:
    python examples/callback_echo.py

Same behaviour as simple_echo.py but uses the callback API instead
of a manual polling loop.  Register handlers with ``@wl.on_message``
and let ``wl.run_forever()`` do the polling in the background.

Set ``LOGLEVEL=DEBUG`` to see raw protocol messages.
"""

from __future__ import annotations

import logging
import os

from weilink import WeiLink

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    wl = WeiLink()
    wl.login()

    @wl.on_message
    def handle(msg):
        if not msg.text:
            return

        logger.info("Received from %s: %s", msg.from_user, msg.text)

        ok = wl.send(msg.from_user, f"Echo: {msg.text}")
        if ok:
            logger.info("Replied to %s", msg.from_user)
        else:
            logger.warning("Failed to reply to %s", msg.from_user)

    print(f"\nBot {wl.bot_id} is running. Send a message in WeChat to start.\n")

    # Blocks until Ctrl+C / SIGTERM, then calls wl.close() automatically
    wl.run_forever()


if __name__ == "__main__":
    main()
