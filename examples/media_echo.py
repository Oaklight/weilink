"""Media echo bot - receives and echoes back text, images, voice, files, video.

Usage:
    pip install weilink[media]
    python examples/media_echo.py

The bot receives WeChat messages of all types and echoes them back.
Text messages are echoed as text; media messages are downloaded and re-sent.
"""

from __future__ import annotations

import logging

from weilink import MessageType, WeiLink

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    wl = WeiLink()
    wl.login()

    print(f"\nBot {wl.bot_id} is running. Send any message in WeChat.\n")

    try:
        while True:
            messages = wl.recv(timeout=35.0)

            for msg in messages:
                user = msg.from_user
                logger.info(
                    "Received %s from %s (ctx=%s)",
                    msg.msg_type.name,
                    user,
                    msg.context_token[:20] if msg.context_token else "None",
                )

                if msg.msg_type == MessageType.TEXT:
                    if msg.text:
                        ok = wl.send(user, f"Echo: {msg.text}")
                        logger.info("Text reply: %s", "ok" if ok else "failed")

                elif msg.msg_type == MessageType.IMAGE:
                    logger.info(
                        "Image: %dx%d, key=%s",
                        msg.image.thumb_width if msg.image else 0,
                        msg.image.thumb_height if msg.image else 0,
                        msg.image.media.aes_key[:16] if msg.image else "?",
                    )
                    try:
                        data = wl.download(msg)
                        logger.info("Downloaded image: %d bytes", len(data))
                        ok = wl.send_image(user, data)
                        logger.info("Image echo: %s", "ok" if ok else "failed")
                    except Exception as e:
                        logger.error("Image handling failed: %s", e)
                        wl.send(user, f"[Image received but echo failed: {e}]")

                elif msg.msg_type == MessageType.VOICE:
                    logger.info(
                        "Voice: %ds, text=%s",
                        msg.voice.playtime if msg.voice else 0,
                        repr(msg.voice.text[:30])
                        if msg.voice and msg.voice.text
                        else "None",
                    )
                    try:
                        data = wl.download(msg)
                        logger.info("Downloaded voice: %d bytes", len(data))
                        # Echo as text if transcription available, otherwise re-send
                        if msg.voice and msg.voice.text:
                            wl.send(
                                user, f"[Voice {msg.voice.playtime}s]: {msg.voice.text}"
                            )
                        else:
                            ok = wl.send_voice(user, data)
                            logger.info("Voice echo: %s", "ok" if ok else "failed")
                    except Exception as e:
                        logger.error("Voice handling failed: %s", e)
                        wl.send(user, f"[Voice received but echo failed: {e}]")

                elif msg.msg_type == MessageType.FILE:
                    fname = msg.file.file_name if msg.file else "unknown"
                    fsize = msg.file.file_size if msg.file else "?"
                    logger.info("File: %s (%s bytes)", fname, fsize)
                    try:
                        data = wl.download(msg)
                        logger.info("Downloaded file: %d bytes", len(data))
                        ok = wl.send_file(user, data, fname)
                        logger.info("File echo: %s", "ok" if ok else "failed")
                    except Exception as e:
                        logger.error("File handling failed: %s", e)
                        wl.send(user, f"[File '{fname}' received but echo failed: {e}]")

                elif msg.msg_type == MessageType.VIDEO:
                    logger.info(
                        "Video: %ds, %dx%d",
                        msg.video.play_length if msg.video else 0,
                        msg.video.thumb_width if msg.video else 0,
                        msg.video.thumb_height if msg.video else 0,
                    )
                    try:
                        data = wl.download(msg)
                        logger.info("Downloaded video: %d bytes", len(data))
                        ok = wl.send_video(user, data)
                        logger.info("Video echo: %s", "ok" if ok else "failed")
                    except Exception as e:
                        logger.error("Video handling failed: %s", e)
                        wl.send(user, f"[Video received but echo failed: {e}]")

                else:
                    logger.warning("Unknown message type: %s", msg.msg_type)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        wl.close()


if __name__ == "__main__":
    main()
