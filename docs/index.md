# WeiLink

[![PyPI](https://img.shields.io/pypi/v/weilink?color=green)](https://pypi.org/project/weilink/)
[![GitHub Release](https://img.shields.io/github/v/release/Oaklight/weilink?color=green)](https://github.com/Oaklight/weilink/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/weilink?color=green)](https://pypi.org/project/weilink/)

Lightweight Python SDK for the WeChat iLink Bot protocol.

## Features

- **Zero dependencies** — Pure Python standard library
- **Message queue semantics** — `login()` / `send()` / `recv()`
- **Automatic state management** — `context_token` and cursor handled internally
- **Credential persistence** — Token saved after QR login

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
- Text only in v0.1 — media support planned
- Tencent may terminate iLink service at any time

## Acknowledgments

- Terminal QR code rendering based on [nayuki/QR-Code-generator](https://github.com/nayuki/QR-Code-generator) (MIT License)
