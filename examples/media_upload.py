"""Pre-upload media and reuse it across multiple sends.

Usage:
    python examples/media_upload.py IMAGE_PATH [USER_ID]

Demonstrates the ``upload()`` / ``send()`` separation:

1. Pre-upload a local file to CDN once via ``wl.upload()``.
2. Wait for a user to send a message (to obtain a context_token).
3. Send the pre-uploaded media to the user — no re-upload needed.
4. On the next message from the same user, send it again to prove
   that the ``UploadedMedia`` reference is reusable.

This is useful when you want to send the same file to many users
without uploading it each time.

Set ``LOGLEVEL=DEBUG`` to see raw protocol messages.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from weilink import WeiLink

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Map file extension to upload media type
_EXT_TO_TYPE: dict[str, str] = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".bmp": "image",
    ".webp": "image",
    ".mp3": "voice",
    ".wav": "voice",
    ".silk": "voice",
    ".amr": "voice",
    ".mp4": "video",
    ".mov": "video",
    ".avi": "video",
}


def _guess_media_type(path: Path) -> str:
    """Guess media type from file extension, default to 'file'."""
    return _EXT_TO_TYPE.get(path.suffix.lower(), "file")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} FILE_PATH [USER_ID]")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    # Optional: target a specific user (skip waiting for message)
    target_user = sys.argv[2] if len(sys.argv) > 2 else None

    media_type = _guess_media_type(file_path)
    file_data = file_path.read_bytes()

    wl = WeiLink()
    wl.login()

    print(f"\nBot {wl.bot_id} is running.")
    print(f"File: {file_path} ({len(file_data)} bytes, type={media_type})")

    if not target_user:
        print("Waiting for a message to get a target user...\n")

    try:
        # Step 1: Get target user
        if not target_user:
            while True:
                messages = wl.recv(timeout=35.0)
                for msg in messages:
                    target_user = msg.from_user
                    print(
                        f"Got message from {target_user}: {msg.text or msg.msg_type.name}"
                    )
                    break
                if target_user:
                    break

        # Step 2: Pre-upload once
        print(f"\n[1] Uploading {file_path.name} to CDN...")
        uploaded = wl.upload(
            to=target_user,
            data=file_data,
            media_type=media_type,
            file_name=file_path.name,
        )
        print(f"    Uploaded! filekey={uploaded.filekey[:16]}...")
        print(f"    cipher_size={uploaded.cipher_size}, file_size={uploaded.file_size}")

        # Step 3: Send using the UploadedMedia reference
        print(f"\n[2] Sending pre-uploaded {media_type} to {target_user}...")
        send_kwargs = {media_type: uploaded}
        if media_type == "file":
            send_kwargs["file_name"] = file_path.name
        result = wl.send(target_user, **send_kwargs)
        print(
            f"    Result: {'ok' if result else 'FAILED'} (remaining={result.remaining})"
        )

        # Step 4: Wait for another message and re-send the same upload
        print(
            "\n[3] Send another message to receive the same file again (no re-upload)..."
        )
        while True:
            messages = wl.recv(timeout=35.0)
            for msg in messages:
                if msg.from_user == target_user:
                    print(f"    Got: {msg.text or msg.msg_type.name}")
                    print("    Re-sending same UploadedMedia...")
                    result = wl.send(target_user, **send_kwargs)
                    print(
                        f"    Result: {'ok' if result else 'FAILED'} (remaining={result.remaining})"
                    )
                    print("\nDone! The same file was sent twice with only one upload.")
                    return
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        wl.close()


if __name__ == "__main__":
    main()
