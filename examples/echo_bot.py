"""Echo bot using OpenAI-compatible API as AI backend.

Usage:
    export OPENAI_API_KEY="your-key"
    export OPENAI_BASE_URL="https://api.openai.com/v1"  # or any compatible endpoint
    python examples/echo_bot.py

The bot receives WeChat messages, forwards them to the AI model,
and replies with the model's response.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request

from weilink import WeiLink

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# AI backend configuration
API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "You are a helpful assistant. Reply concisely in the same language as the user.",
)


def chat_completion(user_text: str) -> str:
    """Call OpenAI-compatible chat completion API.

    Args:
        user_text: User message text.

    Returns:
        Model's reply text.
    """
    url = f"{BASE_URL}/chat/completions"
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "max_tokens": 1024,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except (urllib.error.URLError, KeyError, IndexError) as e:
        logger.error("AI API error: %s", e)
        return f"[Error: {e}]"


def main() -> None:
    if not API_KEY:
        print("Error: OPENAI_API_KEY environment variable is required.")
        print("Usage:")
        print('  export OPENAI_API_KEY="your-key"')
        print("  python examples/echo_bot.py")
        sys.exit(1)

    wl = WeiLink()
    wl.login()

    print(f"\nBot {wl.bot_id} is running. Send a message in WeChat to start.\n")

    try:
        while True:
            messages = wl.recv(timeout=35.0)

            for msg in messages:
                if not msg.text:
                    continue

                logger.info("Received from %s: %s", msg.from_user, msg.text)

                # Show typing indicator
                wl.send_typing(msg.from_user)

                # Get AI response
                reply = chat_completion(msg.text)

                # Send reply and cancel typing
                ok = wl.send(msg.from_user, reply)
                wl.stop_typing(msg.from_user)

                if ok:
                    logger.info("Replied to %s: %s", msg.from_user, reply[:80])
                else:
                    logger.warning("Failed to reply to %s", msg.from_user)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        wl.close()


if __name__ == "__main__":
    main()
