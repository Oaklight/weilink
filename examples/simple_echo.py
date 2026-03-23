"""Simple echo bot - no external dependencies.

Usage:
    python examples/simple_echo.py

The bot receives WeChat messages and echoes them back.
"""

from __future__ import annotations

import logging

from weilink import WeiLink

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    wl = WeiLink()
    wl.login()

    print(f"\nBot {wl.bot_id} is running. Send a message in WeChat to start.\n")

    try:
        while True:
            messages = wl.recv(timeout=35.0)

            for msg in messages:
                if not msg.text:
                    continue

                logger.info(
                    "Received from %s: %s (ctx=%s)",
                    msg.from_user,
                    msg.text,
                    msg.context_token[:20] if msg.context_token else "None",
                )

                ok = wl.send(msg.from_user, f"Echo: {msg.text}")
                if ok:
                    logger.info("Replied to %s", msg.from_user)
                else:
                    logger.warning("Failed to reply to %s", msg.from_user)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        wl.close()


if __name__ == "__main__":
    main()
