---
title: Home
hide:
  - navigation
---

# WeiLink

[![PyPI](https://img.shields.io/pypi/v/weilink?color=green)](https://pypi.org/project/weilink/)
[![PyPI pre-release](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/Oaklight/9f3a274eecbc4df4e1ae5d0f0601e501/raw/pypi-badge.json)](https://pypi.org/project/weilink/#history)
[![GitHub Release](https://img.shields.io/github/v/release/Oaklight/weilink?color=green)](https://github.com/Oaklight/weilink/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

轻量级微信 iLink Bot 协议 Python SDK。

## 特性

- **零运行时依赖** — AES 媒体加密通过 ctypes 调用 OpenSSL，纯 Python 自动兜底
- **消息队列语义** — `login()` / `send()` / `recv()`
- **自动状态管理** — 内部处理 `context_token` 和游标
- **凭证持久化** — 扫码登录后自动保存 Token
- **统一 CLI** — 单一 `weilink` 命令，包含 `admin` 和 `mcp` 子命令
- **Web 管理面板** — 可选的浏览器 UI，支持会话管理、扫码登录，可 [Docker 部署](usage/docker.md)
- **MCP 服务器** — 可选的 [MCP](usage/mcp.md) 集成，支持 stdio/SSE/streamable-http 传输（`pip install weilink[mcp]`）

## 快速开始

```python
from weilink import WeiLink

wl = WeiLink()
wl.login()

messages = wl.recv()
for msg in messages:
    wl.send(msg.from_user, f"Echo: {msg.text}")

wl.close()
```

## 重要限制

- 无法主动发起对话 — 用户必须先发送消息
- 24 小时不活跃窗口 — 超时后机器人消息将被丢弃
- 腾讯可能随时终止 iLink 服务

## 致谢

- QR 码终端渲染基于 [nayuki/QR-Code-generator](https://github.com/nayuki/QR-Code-generator)（MIT 许可）
- AES-128 密码核心源自 [bozhu/AES-Python](https://github.com/bozhu/AES-Python)（MIT 许可），已重写为 Python 3 并新增 ECB 模式和 PKCS7 填充
