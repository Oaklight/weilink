"""Download received media to local disk.

Usage:
    python examples/media_download.py [SAVE_DIR]

The bot waits for media messages (image, voice, file, video), downloads
them from the WeChat CDN, and saves them to a local directory.  Text
messages are acknowledged but not saved.

Files are saved under ``./downloads/`` by default.  Pass a custom path
as the first argument to change the save location.

Set ``LOGLEVEL=DEBUG`` to see raw protocol messages.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from weilink import MessageType, WeiLink

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# File extensions by message type
_EXT: dict[MessageType, str] = {
    MessageType.IMAGE: ".jpg",
    MessageType.VOICE: ".silk",
    MessageType.VIDEO: ".mp4",
}


def _save_path(save_dir: Path, msg_type: MessageType, msg: object) -> Path:
    """Build a unique save path for a media message."""
    from weilink.models import Message

    assert isinstance(msg, Message)
    mid = msg.message_id or 0

    # Use original file name for FILE type
    if msg_type == MessageType.FILE and msg.file:
        name = msg.file.file_name or f"{mid}.bin"
    else:
        name = f"{mid}{_EXT.get(msg_type, '.bin')}"

    path = save_dir / name
    # Avoid overwriting — append counter if file exists
    if path.exists():
        stem, suffix = path.stem, path.suffix
        i = 1
        while path.exists():
            path = save_dir / f"{stem}_{i}{suffix}"
            i += 1
    return path


def main() -> None:
    save_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./downloads")
    save_dir.mkdir(parents=True, exist_ok=True)

    wl = WeiLink()
    wl.login()

    print(f"\nBot {wl.bot_id} is running.")
    print(f"Media will be saved to: {save_dir.resolve()}\n")

    try:
        while True:
            messages = wl.recv(timeout=35.0)

            for msg in messages:
                user = msg.from_user

                if msg.msg_type == MessageType.TEXT:
                    logger.info("Text from %s: %s", user, msg.text)
                    wl.send(user, f"Got it: {msg.text}")
                    continue

                if msg.msg_type not in (
                    MessageType.IMAGE,
                    MessageType.VOICE,
                    MessageType.FILE,
                    MessageType.VIDEO,
                ):
                    logger.warning("Unsupported type: %s", msg.msg_type.name)
                    continue

                logger.info("Received %s from %s", msg.msg_type.name, user)

                try:
                    data = wl.download(msg)
                except Exception as e:
                    logger.error("Download failed: %s", e)
                    wl.send(user, f"[Download failed: {e}]")
                    continue

                path = _save_path(save_dir, msg.msg_type, msg)
                path.write_bytes(data)
                logger.info(
                    "Saved %s (%d bytes) -> %s", msg.msg_type.name, len(data), path
                )

                wl.send(
                    user,
                    f"Saved {msg.msg_type.name} ({len(data)} bytes) to {path.name}",
                )

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        wl.close()


if __name__ == "__main__":
    main()
