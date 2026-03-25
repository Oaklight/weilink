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
- **引用消息解析** — `Message.ref_msg` 暴露用户回复中被引用的原始消息
- **统一 CLI** — 单一 `weilink` 命令，包含 `admin`、`mcp` 和 `openapi` 子命令
- **Web 管理面板** — 可选的浏览器 UI，支持会话管理、扫码登录，可 [Docker 部署](usage/docker.md)
- **MCP / OpenAPI 服务器** — 可选的 [MCP](usage/mcp.md) 和 [OpenAPI](usage/openapi.md) 服务器，用于 AI Agent 和 REST 集成（`pip install weilink[server]`）
- **Docker 就绪** — 多平台容器镜像发布在 [Docker Hub](https://hub.docker.com/r/oaklight/weilink)（amd64、arm64、armv7）

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
