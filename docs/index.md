---
title: Home
hide:
  - navigation
---

# WeiLink

[![PyPI version](https://img.shields.io/pypi/v/weilink?color=green)](https://pypi.org/project/weilink/)
[![GitHub Release](https://img.shields.io/github/v/release/Oaklight/weilink?color=green)](https://github.com/Oaklight/weilink/releases)

Lightweight Python SDK for the WeChat iLink Bot protocol.

## Features

- **Zero runtime dependencies** — AES media encryption uses OpenSSL via ctypes with pure-Python fallback
- **Message queue semantics** — `login()` / `send()` / `recv()`
- **Automatic state management** — `context_token` and cursor handled internally
- **Credential persistence** — Token saved after QR login
- **Web admin panel** — Optional browser UI for session management, QR login, and [Docker deployment](usage/docker.md)
- **MCP server** — Optional [MCP](usage/mcp.md) integration for AI agents (`pip install weilink[mcp]`)

## Quick Start

```python
from weilink import WeiLink

wl = WeiLink()
wl.login()

messages = wl.recv()
for msg in messages:
    wl.send(msg.from_user, f"Echo: {msg.text}")

wl.close()
```

## Important Limitations

- Cannot initiate conversations — user must message first
- 24-hour inactivity window — bot messages discarded after 24h
- Tencent may terminate iLink service at any time

## Acknowledgments

- Terminal QR code rendering based on [nayuki/QR-Code-generator](https://github.com/nayuki/QR-Code-generator) (MIT License)
- AES-128 cipher core derived from [bozhu/AES-Python](https://github.com/bozhu/AES-Python) (MIT License), rewritten for Python 3 with ECB mode and PKCS7 padding added
