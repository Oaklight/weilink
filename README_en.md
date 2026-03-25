# WeiLink

[![PyPI](https://img.shields.io/pypi/v/weilink?color=green)](https://pypi.org/project/weilink/)
[![PyPI pre-release](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/Oaklight/9f3a274eecbc4df4e1ae5d0f0601e501/raw/pypi-badge.json)](https://pypi.org/project/weilink/#history)
[![GitHub Release](https://img.shields.io/github/v/release/Oaklight/weilink?color=green)](https://github.com/Oaklight/weilink/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/weilink?color=green)](https://pypi.org/project/weilink/)

Lightweight Python SDK for the WeChat iLink Bot protocol.

[中文](README_zh.md)

## Features

- **Zero runtime dependencies** — AES media encryption uses OpenSSL via ctypes with pure-Python fallback
- **Message queue semantics** — Three core methods: `login()` / `send()` / `recv()`
- **Automatic state management** — `context_token` and sync cursor handled internally
- **Credential persistence** — Token saved after QR login, survives restarts
- **Typing indicator** — Support for "typing..." status
- **Unified CLI** — Single `weilink` command with `admin` and `mcp` subcommands
- **Web admin panel** — Optional browser UI for session management, QR login, and Docker deployment
- **MCP server** — Optional [MCP](https://modelcontextprotocol.io/) integration for AI agents with stdio/SSE/streamable-http transports (`pip install weilink[mcp]`)

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
- **Service may be terminated** — Tencent can discontinue the iLink API at any time

## Admin Panel

A built-in web UI for session management, QR login, and status monitoring:

```bash
pip install weilink[server]
weilink admin -p 8080
```

![Admin Panel](https://raw.githubusercontent.com/Oaklight/weilink/docs_en/docs/assets/admin_panel.png)

## API

| Method | Description |
|--------|-------------|
| `login(force=False)` | QR code login, reuses existing credentials |
| `recv(timeout=35.0)` | Long-poll for incoming messages |
| `send(to, text, *, image, voice, file, video, file_name)` | Send text and/or media (image/voice/file/video), returns `bool` |
| `download(msg)` | Download media from a received message |
| `send_typing(to)` | Show "typing" indicator |
| `stop_typing(to)` | Cancel "typing" indicator |
| `close()` | Save state and clean up |
| `is_connected` | Whether logged in (property) |
| `bot_id` | Current bot ID (property) |

## Protocol References

- [iLink Bot API Technical Analysis](https://github.com/hao-ji-xing/openclaw-weixin/blob/main/weixin-bot-api.md)
- [Official npm package](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin)
- [WeChat ClawBot Terms of Service](https://github.com/hao-ji-xing/openclaw-weixin/blob/main/protocol.md)

## Acknowledgments

- Terminal QR code rendering based on [nayuki/QR-Code-generator](https://github.com/nayuki/QR-Code-generator) (MIT License)
- AES-128 cipher core derived from [bozhu/AES-Python](https://github.com/bozhu/AES-Python) (MIT License), rewritten for Python 3 with ECB mode and PKCS7 padding added

## License

[MIT](LICENSE)
