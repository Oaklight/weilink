"""Test proactive multi-message sending.

Waits for one incoming message to cache context_token,
then sends 3 consecutive messages to that user.
"""

from __future__ import annotations

import logging
import os
import time

from weilink import WeiLink

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    wl = WeiLink()
    wl.login()

    print(f"\nBot {wl.bot_id} is running.")
    print("Send any message in WeChat to cache context_token, then I'll reply with 3 messages.\n")

    # Wait for one message to get context_token
    user = None
    while not user:
        messages = wl.recv(timeout=35.0)
        for msg in messages:
            user = msg.from_user
            logger.info("Got message from %s, context_token=%s", user, msg.context_token[:20] if msg.context_token else "None")
            break

    # Send 3 consecutive messages
    for i in range(1, 4):
        ok = wl.send(user, f"Proactive message #{i} of 3")
        logger.info("Message #%d: %s", i, "ok" if ok else "FAILED")
        time.sleep(1)

    print("\nDone! Check WeChat for 3 messages.")
    wl.close()


if __name__ == "__main__":
    main()
