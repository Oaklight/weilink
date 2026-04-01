---
description: Manage WeChat messaging via WeiLink — check messages, reply to contacts, download media, manage sessions.
---

# /weilink — WeChat Communication

Arguments: $ARGUMENTS

## Available MCP Tools

### Messaging
- **recv** — Poll for new messages (timeout configurable, default 5s)
- **send** — Send text, image, file, video, or voice to a WeChat user
- **download** — Download media from a received message by message_id
- **history** — Query past messages with filters (user, type, direction, time range, text search)

### Session Management
- **sessions** — List all bot sessions and connection status
- **login** — Start QR code login for a new or existing session
- **logout** — Disconnect a session
- **rename_session** — Rename a bot session
- **set_default** — Set the default session

## Quick Workflows

### Check new messages
Use `recv` to poll for new messages, or `history` with a `since` filter for older ones.

### Reply to someone
1. Get the user ID from a received message (`from_user` field, format: `wxid_xxx@im.wechat`)
2. Use `send` with `to=<user_id>` and `text=<reply>`

### Search message history
Use `history` with filters:
- `user_id` — filter by contact
- `text_contains` — full-text search
- `since` / `until` — time range (ISO 8601 or unix ms)
- `direction` — "received" or "sent"
- `msg_type` — TEXT, IMAGE, VOICE, FILE, VIDEO

### Send media
Use `send` with the appropriate path parameter:
- `image_path` — send an image
- `file_path` + `file_name` — send a file
- `video_path` — send a video
- `voice_path` — send a voice message

### Download received media
Use `download` with the `message_id` from a received message.
Files are saved to `~/.weilink/downloads/` by default (override with `save_dir`).

## Important Notes

- **Message quota**: Each context_token allows 10 outbound messages. After that, wait for the user to send a new inbound message.
- **Text limit**: Messages must be <= 16 KiB UTF-8. Split longer content.
- **Session**: When multiple sessions exist, `send` auto-routes to the session holding a valid context_token for the target user.
- **Login**: Run `login` to scan a QR code. One WeChat account can only bind to one bot at a time.

## Dispatch on $ARGUMENTS

- **(empty)** or **status** — Show session status and recent message summary
- **check** or **messages** — Poll for new messages
- **reply `<user>` `<text>`** — Send a text reply
- **history `<query>`** — Search message history
- Other — Interpret user intent and use appropriate tools
