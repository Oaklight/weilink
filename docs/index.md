---
hide:
  - navigation
---

# WeiLink

[![PyPI version](https://img.shields.io/pypi/v/weilink?color=green)](https://pypi.org/project/weilink/)
[![GitHub Release](https://img.shields.io/github/v/release/Oaklight/weilink?color=green)](https://github.com/Oaklight/weilink/releases)

轻量级微信 iLink Bot 协议 Python SDK。

## 特性

- **依赖精简** — 仅需 `pycryptodome` 用于 AES 媒体加密
- **消息队列语义** — `login()` / `send()` / `recv()`
- **自动状态管理** — 内部处理 `context_token` 和游标
- **凭证持久化** — 扫码登录后自动保存 Token

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
