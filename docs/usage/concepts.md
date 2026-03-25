# Core Concepts

This page explains the key concepts and design decisions behind WeiLink, helping you understand how the pieces fit together.

## iLink Protocol

iLink is Tencent's official bot protocol for WeChat. It provides a set of REST API endpoints that allow developers to register a bot and interact with WeChat users programmatically.

WeiLink is a lightweight Python SDK that wraps the iLink protocol, providing a clean interface for login, messaging, and media handling — with zero runtime dependencies.

## Bot

A **bot** is an application registered on the iLink platform. Each bot has a unique `bot_id` (e.g. `abc123@im.bot`).

!!! warning "One account, one bot"
    A WeChat account can only be bound to **one bot at a time**. Logging into a new bot automatically unbinds the account from the previous bot.

## Session

A **session** represents the binding between a WeChat account and a bot.

```python
wl = WeiLink()

# Default session
wl.login()

# Named session — a different WeChat account on the same bot
wl.login(name="work")
```

- The **default session** is created automatically when you instantiate `WeiLink`.
- **Named sessions** allow one bot to serve multiple WeChat accounts simultaneously.
- Each session has its own login credentials, stored under `~/.weilink/<session_name>/`.

### Default Session

When multiple sessions are active, one is designated as the **default**. The default session is used for operations like `wl.bot_id` and `wl.is_connected`.

```python
wl.set_default("work")  # switch default to the "work" session
```

The default session choice persists across restarts via `~/.weilink/.default_session`.

See [Multi-Session](multi_session.md) for detailed usage.

## User

A **user** is a WeChat account that has messaged the bot. Users are identified by their `user_id` (e.g. `wxid_xxx@im.wechat`).

The bot **cannot initiate a conversation** — it can only reply to users who have sent a message first.

## Context Token

A **context_token** is a short-lived credential issued by the iLink server when a user sends a message. The bot needs a valid context_token to send messages back to that user.

Key properties:

- **Per-user** — each user has their own context_token.
- **24-hour window** — tokens expire roughly 24 hours after the user's last message. After expiry, messages sent by the bot are **silently discarded** (no error is returned).
- **Auto-managed** — the SDK automatically captures and updates context_tokens from incoming messages.
- **Persisted** — tokens are saved to `~/.weilink/<session>/contexts.json` with timestamps, surviving restarts.

```
User sends message → iLink issues context_token → SDK stores it
Bot calls send()   → SDK uses stored context_token → iLink delivers message
```

!!! tip "Proactive messaging"
    As long as a valid context_token exists (from a previous conversation or loaded from disk), you can call `send()` without calling `recv()` first.

!!! tip "Auto-recv"
    Pass `auto_recv=True` to `send()` to automatically call `recv()` before sending, ensuring fresh context tokens. The MCP server enables this by default.

## Quoted Messages (ref_msg)

When a user **replies to** (quotes) a previous message, the iLink protocol includes the referenced message content in the payload. The SDK parses this into a `RefMessage` object accessible via `Message.ref_msg`.

```python
for msg in wl.recv():
    if msg.ref_msg is not None:
        print(f"Quoted: {msg.ref_msg.text}")
    print(f"New: {msg.text}")
```

`RefMessage` carries the same media fields as `Message` (`text`, `image`, `voice`, `file`, `video`) but **no metadata** (no `from_user`, `message_id`, or `timestamp`) — the protocol does not provide these for quoted messages.

!!! note
    When the quoted message is an image or other media-only message, some WeChat clients do not include `ref_msg` in the protocol payload. In that case, `msg.ref_msg` will be `None`.

## Message Flow

### Receiving

```
WeChat User → WeChat → iLink Server → WeiLink SDK (recv) → Your Code
```

`recv()` uses long-polling: it blocks until new messages arrive or the timeout expires. When multiple sessions are active, all sessions are polled concurrently.

### Sending

```
Your Code → WeiLink SDK (send) → iLink Server → WeChat → WeChat User
```

`send()` automatically routes to the correct session based on the target `user_id`. If the user exists in multiple sessions, the most recently active session is used.

### Media

The iLink protocol enforces **one media item per message**. When you pass both `text` and `image` to `send()`, the SDK automatically splits them into separate messages.

Media files (images, voice, video, files) are encrypted and uploaded to Tencent's CDN before delivery. The SDK handles encryption, upload, and decryption transparently.
