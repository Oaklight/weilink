"""Test proactive multimodal message sending.

Sends image, file, and video using persisted context_token (no recv needed).
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

USER = "o9cq806ISUPJQw-xWEx2tGb4RcSY@im.wechat"


def main() -> None:
    wl = WeiLink()
    wl.login()
    print(f"Bot {wl.bot_id} ready.\n")

    # 1. Send text
    print("[1/4] Sending text...")
    ok = wl.send(USER, "Multimodal proactive test starting!")
    print(f"  Text: {'ok' if ok else 'FAILED'}")
    time.sleep(1)

    # 2. Send image
    img_path = os.path.expanduser("~/Downloads/image.png")
    print(f"[2/4] Sending image: {img_path}")
    with open(img_path, "rb") as f:
        img_data = f.read()
    print(f"  Image size: {len(img_data)} bytes")
    ok = wl.send_image(USER, img_data)
    print(f"  Image: {'ok' if ok else 'FAILED'}")
    time.sleep(1)

    # 3. Send file (PDF)
    pdf_path = os.path.expanduser("~/Downloads/2406.10149v2.pdf")
    print(f"[3/4] Sending file: {pdf_path}")
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()
    print(f"  File size: {len(pdf_data)} bytes")
    ok = wl.send_file(USER, pdf_data, "2406.10149v2.pdf")
    print(f"  File: {'ok' if ok else 'FAILED'}")
    time.sleep(1)

    # 4. Send video
    vid_path = os.path.expanduser("~/Downloads/VID_20250210_151251.mp4")
    print(f"[4/4] Sending video: {vid_path}")
    with open(vid_path, "rb") as f:
        vid_data = f.read()
    print(f"  Video size: {len(vid_data)} bytes")
    try:
        ok = wl.send_video(USER, vid_data)
        print(f"  Video: {'ok' if ok else 'FAILED'}")
    except Exception as e:
        print(f"  Video: FAILED ({e})")

    print("\nDone! Check WeChat.")
    wl.close()


if __name__ == "__main__":
    main()
