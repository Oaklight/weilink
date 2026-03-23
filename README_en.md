# WeiLink

Lightweight Python SDK for the WeChat iLink Bot protocol.

[中文](README_zh.md)

## Features

- **Zero dependencies** — Pure Python standard library, no third-party packages
- **Message queue semantics** — Three core methods: `login()` / `send()` / `recv()`
- **Automatic state management** — `context_token` and sync cursor handled internally
- **Credential persistence** — Token saved after QR login, survives restarts
- **Typing indicator** — Support for "typing..." status

## Install

```bash
pip install weilink
```

## Quick Start

```python
from weilink import WeiLink

wl = WeiLink()
wl.login()

# Receive messages
messages = wl.recv()
for msg in messages:
    print(f"{msg.from_user}: {msg.text}")

# Reply
wl.send(msg.from_user, "Got it!")

wl.close()
```

## How It Works

WeiLink wraps the WeChat iLink Bot protocol (the underlying protocol of the ClawBot plugin), exposing a message-queue-style interface:

```
login()  →  QR scan to obtain credentials (persisted)
recv()   →  Long-poll for messages (35s timeout)
send()   →  Reply to a user (context_token auto-attached)
```

### Important Limitations

- **Cannot initiate conversations** — User must message the bot first
- **24-hour window** — Messages from the bot are discarded if the user hasn't sent anything in 24 hours
- **Text only** — Current version does not support images/files/voice/video
- **Service may be terminated** — Tencent can discontinue the iLink API at any time

## API

| Method | Description |
|--------|-------------|
| `login(force=False)` | QR code login, reuses existing credentials |
| `recv(timeout=35.0)` | Long-poll for incoming messages |
| `send(to, text)` | Send a text message, returns `bool` |
| `send_typing(to)` | Show "typing" indicator |
| `stop_typing(to)` | Cancel "typing" indicator |
| `close()` | Save state and clean up |
| `is_connected` | Whether logged in (property) |
| `bot_id` | Current bot ID (property) |

## Protocol References

- [iLink Bot API Technical Analysis](https://github.com/hao-ji-xing/openclaw-weixin/blob/main/weixin-bot-api.md)
- [Official npm package](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin)
- [WeChat ClawBot Terms of Service](https://github.com/hao-ji-xing/openclaw-weixin/blob/main/protocol.md)

## License

[MIT](LICENSE)
